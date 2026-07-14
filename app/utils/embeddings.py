import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from collections import OrderedDict
from threading import Lock, RLock
import numpy as np
import pandas as pd
import torch
from flask import session, url_for, flash, current_app
from transformers import AutoModel, AutoTokenizer
from werkzeug.utils import secure_filename, redirect

from app.models import FAQ, DraftFAQ, db, Logs, User, FutureIssueTracker
from sqlalchemy import func, case


# -------------------------------------------------------------------
# Helpers: normalize, sanitize, file check
# -------------------------------------------------------------------
def normalize_text(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text

def sanitize_cell(value):
    # Handle memoryview objects and other non-string types
    if value is None:
        return ''
    
    # Convert memoryview to string first
    if isinstance(value, memoryview):
        try:
            value = value.tobytes().decode('utf-8')
        except (UnicodeDecodeError, AttributeError):
            value = str(value)
    
    s = str(value).strip()
    if s.startswith(('=', '+', '-', '@')):
        s = "'" + s
    return s

def allowed_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config['ALLOWED_EXTENSIONS']

def allowed_datadump_filename(filename):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('DATADUMP_ALLOWED_EXTENSIONS', set())

def save_datadump_file(file_storage):
    filename = secure_filename(file_storage.filename)
    # prepend uuid to avoid collisions
    uid = uuid.uuid4().hex
    stored_name = f"{uid}_{filename}"
    upload_folder = current_app.config['DATADUMP_UPLOAD_FOLDER']
    path = os.path.join(upload_folder, stored_name)
    file_storage.save(path)
    return stored_name, path


# -------------------------------------------------------------------
# Embedding model (private, on-prem): lazy-load + correct sentence pooling
# -------------------------------------------------------------------
_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
_EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "").strip().lower()  # "", "cpu", "cuda"
_tokenizer = None
_model = None
_device = None
_model_load_lock = RLock()  # Reentrant lock for thread-safe lazy loading (allows nested calls from _get_device)
_emb_cache = OrderedDict()
_emb_cache_lock = Lock()
_emb_cache_max = int(os.getenv("EMBEDDING_CACHE_SIZE", "5000"))


def _get_device():
    """
    Thread-safe device initialization (CPU/GPU selection).
    Uses double-checked locking to prevent race conditions.
    """
    global _device
    # Fast path: check without lock if already initialized
    if _device is not None:
        return _device

    # Slow path: acquire lock and double-check
    with _model_load_lock:  # Reuse same lock (device init happens before model load)
        # Double-check: another thread may have initialized it while we waited
        if _device is not None:
            return _device

        # Initialize device (only one thread reaches here)
        if _EMBEDDING_DEVICE in ("cpu", "cuda"):
            _device = torch.device(_EMBEDDING_DEVICE)
        else:
            _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return _device


def _load_embedding_model():
    """
    Thread-safe lazy-load tokenizer/model once per process.
    Uses double-checked locking to prevent race conditions in multi-threaded environments.
    Note: this uses local HF cache; for fully offline deployments, pre-populate the cache.
    Returns None if model cannot be loaded (offline environment without cached model).
    """
    global _tokenizer, _model
    # Fast path: check without lock if already loaded
    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model

    # Slow path: acquire lock and double-check
    with _model_load_lock:
        # Double-check: another thread may have loaded it while we waited for the lock
        if _tokenizer is not None and _model is not None:
            return _tokenizer, _model

        # Load model (only one thread reaches here)
        try:
            _tokenizer = AutoTokenizer.from_pretrained(_EMBEDDING_MODEL_NAME, local_files_only=True)
            _model = AutoModel.from_pretrained(_EMBEDDING_MODEL_NAME, local_files_only=True)
            _model.eval()
            _model.to(_get_device())
            return _tokenizer, _model
        except (OSError, EnvironmentError) as e:
            # Model not in cache and cannot download (offline environment)
            current_app.logger.error(f"Cannot load embedding model: {e}. Semantic search will be disabled.")
            return None, None


def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).type_as(last_hidden_state)
    summed = (last_hidden_state * mask).sum(dim=1)
    denom = mask.sum(dim=1).clamp(min=1e-9)
    return summed / denom


def _cache_get(key: str):
    if not key or _emb_cache_max <= 0:
        return None
    with _emb_cache_lock:
        v = _emb_cache.get(key)
        if v is None:
            return None
        _emb_cache.move_to_end(key)
        return v


def _cache_put(key: str, vec: np.ndarray):
    if not key or vec is None or _emb_cache_max <= 0:
        return
    with _emb_cache_lock:
        _emb_cache[key] = vec
        _emb_cache.move_to_end(key)
        while len(_emb_cache) > _emb_cache_max:
            _emb_cache.popitem(last=False)

def validate_question_input(text: str, max_length: int = 5000) -> tuple[bool, str | None]:
    """
    Validate input for embedding generation.
    Returns (is_valid, error_message)
    """
    if not text or not isinstance(text, str):
        return False, "Input must be a non-empty string"
    if len(text) > max_length:
        return False, f"Input exceeds maximum length of {max_length} characters"
    # Check for suspicious patterns (Unicode abuse)
    if len(text.encode('utf-8')) > max_length * 4:
        return False, "Invalid input encoding"
    return True, None


def get_bert_embeddings(text: str):
    if not text:
        return None
    
    # Validate input
    is_valid, error = validate_question_input(text)
    if not is_valid:
        current_app.logger.warning(f"Invalid input rejected: {error}")
        return None
    
    text = str(text)

    # Near-duplicate control + cache key stability
    key = normalize_text(text)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    tokenizer, model = _load_embedding_model()
    if tokenizer is None or model is None:
        # Model not available, return None
        return None
    inputs = tokenizer(text, return_tensors='pt', padding=True, truncation=True, max_length=512)
    inputs = {k: v.to(_get_device()) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)

    # Sentence-transformer style embedding: mask-aware mean pooling.
    pooled = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"])
    emb = pooled.squeeze(0).detach().cpu().numpy().astype(np.float32)
    _cache_put(key, emb)
    return emb


def get_bert_embeddings_batch(texts):
    """
    Batch embed for high QPS / bulk operations.
    Returns list[np.ndarray] aligned with input, with caching.
    """
    if not texts:
        return []

    # Normalize + cache hits
    normed = [normalize_text(str(t or "")) for t in texts]
    out = [None] * len(normed)
    to_compute = []
    to_compute_idx = []
    for i, k in enumerate(normed):
        if not k:
            out[i] = None
            continue
        hit = _cache_get(k)
        if hit is not None:
            out[i] = hit
        else:
            to_compute.append(texts[i])
            to_compute_idx.append(i)

    if not to_compute:
        return out

    tokenizer, model = _load_embedding_model()
    inputs = tokenizer([str(t or "") for t in to_compute], return_tensors='pt', padding=True, truncation=True, max_length=512)
    inputs = {k: v.to(_get_device()) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)
    pooled = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"])
    vecs = pooled.detach().cpu().numpy().astype(np.float32)

    for j, i in enumerate(to_compute_idx):
        k = normed[i]
        v = vecs[j]
        out[i] = v
        _cache_put(k, v)

    return out

def l2_normalize(vec: np.ndarray):
    if vec is None:
        return None
    vec = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm

def set_embedding_for_model(model_obj, text_field: str):
    txt = getattr(model_obj, text_field, '') or ''
    emb = get_bert_embeddings(txt)
    if emb is None:
        model_obj.embedding = None
    else:
        emb = l2_normalize(emb)
        model_obj.embedding = emb.astype(np.float32).tobytes()


# -------------------------------------------------------------------
# Utility functions for auth, roles, logs
# -------------------------------------------------------------------
def add_log(action, user_email):
    try:
        log = Logs(action=action, user_email=user_email, timestamp=datetime.utcnow())
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        try:
            current_app.logger.exception("[LOGGING ERROR] %s", e)
        except Exception:
            pass


def current_user():
    if 'user_id' not in session:
        return None
    return db.session.get(User, session['user_id'])

def get_role():
    role = session.get('role')
    return (role or '').lower()

def is_admin():
    return get_role() == 'admin'

def is_reviewer():
    return get_role() == 'reviewer'

def is_modifier():
    return get_role() == 'modifier'

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        if session.permanent:
            now = datetime.now(timezone.utc)

            if 'last_activity' in session:
                last_activity = session['last_activity']

                if isinstance(last_activity, datetime):
                    # Normalize in case older sessions stored naive datetimes
                    if last_activity.tzinfo is None:
                        last_activity = last_activity.replace(tzinfo=timezone.utc)

                    if now - last_activity > timedelta(hours=8):
                        session.clear()
                        flash("Session expired. Please login again.", "warning")
                        return redirect(url_for('auth.login'))

            session['last_activity'] = now
        
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin():
            flash("Access denied: admin only", "warning")
            return redirect(url_for('auth.index'))
        return f(*args, **kwargs)
    return decorated

# -------------------------------------
# detect future issue helper
# -------------------------------------

def detect_future_issue(text):
    if not text:
        return False

    patterns = [
        r"will be rectified in a future version",
        r"\bwill be addressed in the (next|upcoming|future) version\b",
        r"\bwill be seen in the (next|upcoming|future) version\b",
        r"\bwill be explored in (the )?(next|upcoming|future) versions?\b",
        r"\bplanned for (the )?(next|upcoming|future) (release|version|update)\b",
        r"\bto be fixed in (the )?(next|upcoming|future) (release|version|update)\b",
        r"\b(in|on) the next release\b",
        r"\b(next|upcoming|future) (release|version|update)\b"
    ]
    combined = re.compile("|".join(patterns), re.IGNORECASE)
    return bool(combined.search(text))


def extract_version_from_text(text):
    """Extract version information from text with better patterns"""
    if not text:
        return None
        
    version_patterns = [
        r"version\s*(\d+\.?\d*\.?\d*)",
        r"v(\d+\.?\d*\.?\d*)", 
        r"release\s*(\d+\.?\d*\.?\d*)",
        r"(\d+\.?\d*\.?\d*)"
    ]
    
    for pattern in version_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def create_future_issue(description, related_draft_id=None, related_faq_id=None, 
                   version_detected=None, note=None, source_portal=None, 
                   source_query_date=None, source_query_id=None):
    try:
        # Enhanced version detection from note
        resolution_version = None
        if note:
            extracted_version = extract_version_from_text(note)
            if extracted_version:
                resolution_version = extracted_version
        
        issue = FutureIssueTracker(
            description=description,
            related_draft_id=related_draft_id,
            related_faq_id=related_faq_id,
            version_detected=version_detected or os.getenv("PORTAL_VERSION"),
            note=note,
            source_portal=source_portal,
            source_query_date=source_query_date,
            source_query_id=source_query_id,
            resolution_version=resolution_version
        )
        db.session.add(issue)
        db.session.commit()
        return issue
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to create future issue tracker entry")
        return None


# ------------------------------------------------
# find_related_questions
# ------------------------------------------------
def normalize(v):
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        v = np.frombuffer(v, dtype=np.float32)
    else:
        v = np.array(v, dtype=np.float32)
    norm = np.linalg.norm(v)
    if norm == 0:
        return v
    return v / norm

def get_similarity_threshold() -> float:
    """
    Read from config/env (Config.SIMILARITY_THRESHOLD), fallback 0.75.
    """
    try:
        return float(current_app.config.get("SIMILARITY_THRESHOLD", 0.75))
    except Exception:
        return 0.75


def get_max_distance() -> float:
    # pgvector cosine_distance assumes vectors are normalized; distance ~= 1 - cosine_similarity
    return 1.0 - get_similarity_threshold()


def cosine_sim_from_distance(distance) -> float:
    try:
        return 1.0 - float(distance)
    except Exception:
        return 0.0

def find_related_questions(question, reply, memo_id, state_name):
    search_text = question or reply
    if not search_text:
        return []

    # Get embedding for search text
    search_emb = get_bert_embeddings(search_text)
    if search_emb is None:
        # Model not available, return empty results
        return []
    search_emb = normalize(search_emb)

    # Base query to get all potential FAQs
    query = FAQ.query
    if memo_id:
        query = query.filter_by(memo_id=memo_id)
    if state_name:
        query = query.filter_by(state_name=state_name)

    # Get all FAQs and filter manually
    all_faqs = query.all()
    max_distance = get_max_distance()
    
    results = []
    for faq in all_faqs:
        if faq.embedding:
            # Convert stored bytes back to numpy array
            stored_emb = np.frombuffer(faq.embedding, dtype=np.float32)
            stored_emb = normalize(stored_emb)
            
            # Calculate cosine distance
            distance = 1 - np.dot(search_emb, stored_emb)
            if distance <= max_distance:
                results.append((faq, distance))
    
    # Sort by distance (closest first)
    results.sort(key=lambda x: x[1])
    
    # Apply limit
    limit = current_app.config.get('VECTOR_SEARCH_LIMIT', 50)
    results = results[:limit]
    
    return [(f.subject, f.reply, f.memo_id, f.state_name) for f, _ in results]


def find_related_questions_scored(question, reply, memo_id, state_name):
    """
    Vector search + return similarity for confidence gating.
    Returns list of dicts ordered by best match first.
    """
    search_text = question or reply
    if not search_text:
        return []

    # Get embedding for search text
    search_emb = get_bert_embeddings(search_text)
    if search_emb is None:
        return []
    search_emb = normalize(search_emb)

    # Base query to get all potential FAQs
    query = FAQ.query
    if memo_id:
        query = query.filter_by(memo_id=memo_id)
    if state_name:
        query = query.filter_by(state_name=state_name)

    # Get all FAQs and filter manually
    all_faqs = query.all()
    max_distance = get_max_distance()
    
    results = []
    for faq in all_faqs:
        if faq.embedding:
            # Convert stored bytes back to numpy array
            stored_emb = np.frombuffer(faq.embedding, dtype=np.float32)
            stored_emb = normalize(stored_emb)
            
            # Calculate cosine distance
            distance = 1 - np.dot(search_emb, stored_emb)
            if distance <= max_distance:
                results.append({
                    "question": faq.subject,
                    "reply": faq.reply,
                    "memo_id": faq.memo_id,
                    "state_name": faq.state_name,
                    "distance": float(distance),
                    "similarity": cosine_sim_from_distance(distance),
                })
    
    # Sort by distance (closest first)
    results.sort(key=lambda x: x["distance"])
    
    # Apply limit
    limit = current_app.config.get('VECTOR_SEARCH_LIMIT', 50)
    results = results[:limit]
    
    return results


def fetch_data():
    total_questions = FAQ.query.filter(
        FAQ.state_name.isnot(None),
        FAQ.state_name != ''
    ).count()
    total_states = db.session.query(FAQ.state_name).filter(
        FAQ.state_name.isnot(None),
        FAQ.state_name != ''
    ).distinct().count()
    unanswered_questions = DraftFAQ.query.filter(
        (DraftFAQ.reply.is_(None)) | (DraftFAQ.reply == ''),
        DraftFAQ.state_name.isnot(None),
        DraftFAQ.state_name != ''
    ).count()

    # State-wise: total, answered, unanswered
    state_wise_count = (
        db.session.query(
            FAQ.state_name,
            func.count(FAQ.id).label("total"),
            func.sum(case((FAQ.reply.isnot(None) & (FAQ.reply != ''), 1), else_=0)).label("answered"),
            func.sum(case((FAQ.reply.is_(None) | (FAQ.reply == ''), 1), else_=0)).label("unanswered"),
        )
        .filter(
            FAQ.state_name.isnot(None),
            FAQ.state_name != '',
            FAQ.state_name != 'NaN',
            FAQ.state_name != 'nan',
            FAQ.state_name != 'None'
        )
        .group_by(FAQ.state_name).all()
    )

    return total_questions, total_states, unanswered_questions, state_wise_count


def cleanup_queries_without_states():
    """
    Delete existing queries without valid state_name from database.
    This function cleans up data integrity issues by removing:
    - FAQ entries with null or empty state_name
    - DraftFAQ entries with null or empty state_name
    - AuditQuery entries with null or empty state_name
    Returns counts of deleted records.
    """
    try:
        # Cleanup FAQ table
        faq_deleted = FAQ.query.filter(
            (FAQ.state_name.is_(None)) | 
            (FAQ.state_name == '') |
            (FAQ.state_name == 'NaN') |
            (FAQ.state_name == 'nan') |
            (FAQ.state_name == 'None')
        ).delete()
        
        # Cleanup DraftFAQ table  
        draft_faq_deleted = DraftFAQ.query.filter(
            (DraftFAQ.state_name.is_(None)) | 
            (DraftFAQ.state_name == '') |
            (DraftFAQ.state_name == 'NaN') |
            (DraftFAQ.state_name == 'nan') |
            (DraftFAQ.state_name == 'None')
        ).delete()
        
        # Cleanup AuditQuery table if it exists
        audit_deleted = 0
        try:
            from app.audit_models import AuditQuery
            audit_deleted = AuditQuery.query.filter(
                (AuditQuery.state_name.is_(None)) | 
                (AuditQuery.state_name == '') |
                (AuditQuery.state_name == 'NaN') |
                (AuditQuery.state_name == 'nan') |
                (AuditQuery.state_name == 'None')
            ).delete()
        except ImportError:
            # AuditQuery model not available, skip
            pass
        
        db.session.commit()
        
        current_app.logger.info(f"Cleanup completed: {faq_deleted} FAQ, {draft_faq_deleted} DraftFAQ, {audit_deleted} AuditQuery records deleted")
        
        return {
            'faq_deleted': faq_deleted,
            'draft_faq_deleted': draft_faq_deleted, 
            'audit_deleted': audit_deleted,
            'total_deleted': faq_deleted + draft_faq_deleted + audit_deleted
        }
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Cleanup failed: {str(e)}")
        raise e


def get_embedding(texts):
    """
    Get embeddings for a list of texts.
    Compatible interface for document QA system.
    """
    if isinstance(texts, str):
        texts = [texts]
    
    embeddings = get_bert_embeddings_batch(texts)
    return embeddings


def encode_text(text):
    vec = get_bert_embeddings(text)
    if vec is None:
        return None
    vec = normalize(vec)
    return vec.tobytes()




