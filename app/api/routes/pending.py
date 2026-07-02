import os
import uuid
from datetime import datetime
import pandas as pd
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.models import User, db, FAQ, DraftFAQ, DraftStatus
from app.utils.embeddings import login_required, current_user, fetch_data, get_role, find_related_questions, find_related_questions_scored, \
    sanitize_cell, create_future_issue, is_modifier, detect_future_issue, get_bert_embeddings, normalize_text, normalize as normalize_vector, \
    allowed_file, add_log, encode_text
from flask import current_app
from app.utils.validation import validate_file_mime, validate_file_size

def get_versioned_response_for_question(question):
    """Check if question has been addressed in future issues"""
    from app.models import FutureIssueTracker
    from app.utils.embeddings import normalize_text
    
    # Normalize question for similarity search
    normalized_q = normalize_text(question)
    
    # Find similar addressed future issues using text similarity
    similar_issues = []
    issues = FutureIssueTracker.query.filter(
        FutureIssueTracker.status == 'addressed'
    ).all()
    
    for issue in issues:
        if issue.description:
            # Simple text similarity check
            if normalized_q.lower() in normalize_text(issue.description).lower() or \
               normalize_text(issue.description).lower() in normalized_q.lower():
                similar_issues.append({
                    'issue': issue,
                    'similarity': 0.8,  # High similarity for text match
                    'match_type': 'text'
                })
    
    if similar_issues:
        # Get the most recent addressed issue
        latest_issue = similar_issues[0]['issue']
        
        return {
            'has_versioned_response': True,
            'suggested_response': f"This issue has been addressed. {latest_issue.note or ''}",
            'version_info': latest_issue.version_fixed,
            'fix_date': latest_issue.version_detected,
            'confidence': 'high'
        }
    
    return {'has_versioned_response': False}

pending_bp = Blueprint("pending", __name__)


# -------------------------------
# Pending page
# -------------------------------
@pending_bp.route('/pending', methods=['GET', 'POST'])
@login_required
def pending():
    role = get_role()
    user = current_user()
    email = session.get('email')

    unanswered_main = DraftFAQ.query.filter(
        (DraftFAQ.reply.is_(None)) | (DraftFAQ.reply == '')
    ).filter(
        DraftFAQ.state_name.isnot(None)
    ).filter(
        DraftFAQ.state_name != ''
    ).all()

    distinct_states = (
        db.session.query(DraftFAQ.state_name)
        .filter(
            DraftFAQ.status == DraftStatus.pending.value,
            (DraftFAQ.reply.is_(None)) | (DraftFAQ.reply == ''),
            DraftFAQ.state_name.isnot(None),
            DraftFAQ.state_name != ''
        )
        .distinct()
        .order_by(DraftFAQ.state_name.asc())
        .all()
    )
    distinct_states = [row[0] for row in distinct_states]

    # Fetch pending drafts based on role
    # For "My Queries" - show queries based on role permissions
    # Admin and Reviewer can view all pending questions from all states
    # Modifier and Viewer can view pending questions from their own state
    
    # Base query for pending drafts
    query = DraftFAQ.query.filter(
        (DraftFAQ.reply.is_(None) | (DraftFAQ.reply == ''))
    ).filter(
        DraftFAQ.state_name.isnot(None)
    ).filter(
        DraftFAQ.state_name != ''
    )
    
    # Apply role-based filtering
    if role in ['modifier', 'viewer']:
        # Viewers and modifiers can only see pending questions from their own state
        query = query.filter(DraftFAQ.state_name == user.state_name)
    elif role == 'admin':
        # Admin can see pending and admin_draft status
        query = query.filter(DraftFAQ.status.in_([DraftStatus.pending, DraftStatus.admin_draft]))
    elif role == 'reviewer':
        # Reviewer can see pending status
        query = query.filter(DraftFAQ.status == DraftStatus.pending)
    
    pending_drafts = query.order_by(DraftFAQ.created_at.desc()).all()

    show_state_dropdown = role in ['admin', 'reviewer']
    can_save = role in ['admin', 'reviewer', 'modifier']
    can_delete = role == 'admin'

    # --------------------
    # FILE UPLOAD LOGIC
    # --------------------
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(url_for('pending.pending'))

        file = request.files['file']
        if not file or file.filename == '':
            flash('No selected file.', 'danger')
            return redirect(url_for('pending.pending'))

        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload a CSV or Excel file.', 'danger')
            return redirect(url_for('pending.pending'))

        # Validate MIME type
        allowed_mimes = current_app.config.get('UPLOAD_ALLOWED_MIME_TYPES', set())
        is_valid_mime, mime_error = validate_file_mime(file, allowed_mimes)
        if not is_valid_mime:
            flash(mime_error or 'Invalid file type detected', 'danger')
            return redirect(url_for('pending'))

        # Validate file size
        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 60 * 1024 * 1024 * 1024)
        is_valid_size, size_error = validate_file_size(file, max_size)
        if not is_valid_size:
            flash(size_error or 'File too large', 'danger')
            return redirect(url_for('pending'))

        filename = secure_filename(file.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        safe_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(upload_folder, safe_filename)
        file.save(filepath)

        try:
            if filename.endswith('.csv'):
                try:
                    data = pd.read_csv(filepath, dtype=str)
                except UnicodeDecodeError:
                    data = pd.read_csv(filepath, encoding='latin1', dtype=str)
            else:
                data = pd.read_excel(filepath, dtype=str)

            data.columns = [c.lower().strip() for c in data.columns]

            if 'question' not in data.columns or 'state_name' not in data.columns:
                flash('File must contain both "question" and "state_name" columns.', 'danger')
                return redirect(url_for('pending.pending'))

            merged_pending = 0
            merged_review = 0
            duplicate_count = 0
            skipped_invalid = 0

            uploader = session.get('username') or session.get('email') or 'unknown'

            for _, row in data.iterrows():
                question = sanitize_cell(row.get('question', ''))
                reply = sanitize_cell(row.get('reply', '')) if 'reply' in data.columns else ''
                memo_id = sanitize_cell(row.get('memo_id', ''))
                state_name = sanitize_cell(row.get('state_name', ''))

                if not question or not state_name:
                    skipped_invalid += 1
                    continue
                
                # Additional validation for state_name
                if not state_name or not state_name.strip():
                    skipped_invalid += 1
                    continue

                normq = normalize_text(question)

                existing = (
                    DraftFAQ.query.filter_by(norm_query=normq, state_name=state_name).first() or
                    FAQ.query.filter_by(norm_query=normq, state_name=state_name).first()
                )
                if existing:
                    duplicate_count += 1
                    continue

                draft_entry = DraftFAQ(
                    subject=question,
                    norm_query=normq,
                    reply=reply or None,
                    memo_id=memo_id or None,
                    state_name=state_name,
                    created_by=uploader,
                    status=DraftStatus.admin_draft if reply else DraftStatus.pending
                )

                # PGVECTOR EMBEDDING
                emb = get_bert_embeddings(question)
                if emb is not None:
                    emb = normalize_vector(emb)
                    draft_entry.embedding = emb.astype("float32").tobytes()
                else:
                    draft_entry.embedding = None

                db.session.add(draft_entry)
                try:
                    db.session.commit()
                    if reply:
                        merged_review += 1
                    else:
                        merged_pending += 1

                    if reply and detect_future_issue(reply):
                        # Check if similar issue has been addressed before
                        versioned_response = get_versioned_response_for_question(question)
                        
                        if versioned_response['has_versioned_response']:
                            # Use existing resolved version response instead of future promise
                            create_future_issue(
                                description=f"<b>Question:</b> {question}<br><b>Reply:</b> {reply}",
                                related_draft_id=draft_entry.id,
                                version_detected=versioned_response['version_info'],
                                note=f"Auto-generated response based on resolved issue version {versioned_response['version_info']}",
                                template_response=versioned_response['suggested_response']
                            )
                        else:
                            # Create new future issue
                            create_future_issue(
                                description=f"<b>Question:</b> {question}<br><b>Reply:</b> {reply}",
                                related_draft_id=draft_entry.id,
                                version_detected=os.getenv("PORTAL_VERSION", None)
                            )

                except IntegrityError:
                    db.session.rollback()
                    duplicate_count += 1

            flash(
                f"✅ {merged_pending} added to Pending, "
                f"{merged_review} moved to Review, "
                f"{duplicate_count} duplicates skipped, "
                f"{skipped_invalid} invalid rows skipped.",
                "success"
            )

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error processing uploaded file")
            flash("Failed to process file.", "danger")

        return redirect(url_for('pending.pending'))

    return render_template(
        'pending.html',
        role=role,
        unanswered_main=unanswered_main,
        distinct_states=distinct_states,
        pending_drafts=pending_drafts,
        show_state_dropdown=show_state_dropdown,
        can_save=can_save,
        can_delete=can_delete
    )


@pending_bp.route('/api/pending_questions', methods=['GET'])
@login_required
def get_pending_questions():
    try:
        user = current_user()
        role = get_role()
        state_name = user.state_name
        selected_state = request.args.get('state', '').strip()

        # Debug logging
        current_app.logger.info(f"API request - Role: {role}, State: {state_name}, Selected: {selected_state}")

        # Fetch from DraftFAQ table where reply is missing
        query = DraftFAQ.query.filter(
            (DraftFAQ.reply.is_(None) | (DraftFAQ.reply == ''))
        )
        
        # Filter out queries without state_name
        query = query.filter(DraftFAQ.state_name.isnot(None))
        query = query.filter(DraftFAQ.state_name != '')

        # Apply role-based filtering with status (matching main pending route logic)
        if role in ['modifier', 'viewer']:
            # Viewers and modifiers can only see pending questions from their own state
            query = query.filter(DraftFAQ.state_name == state_name)
            query = query.filter(DraftFAQ.status == DraftStatus.pending)
        elif role == 'admin':
            # Admin can see pending and admin_draft status
            query = query.filter(DraftFAQ.status.in_([DraftStatus.pending, DraftStatus.admin_draft]))
            if selected_state:
                query = query.filter(DraftFAQ.state_name == selected_state)
        elif role == 'reviewer':
            # Reviewer can see pending status
            query = query.filter(DraftFAQ.status == DraftStatus.pending)
            if selected_state:
                query = query.filter(DraftFAQ.state_name == selected_state)

        # Fetch all pending drafts
        pending_drafts = query.order_by(DraftFAQ.id.desc()).all()
        
        current_app.logger.info(f"Found {len(pending_drafts)} pending drafts")
        
        result = []
        for draft in pending_drafts:
            suggested_answer = None

            # 1) Exact match on normalized question + state (strongest signal)
            exact = FAQ.query.filter_by(
                norm_query=draft.norm_query,
                #state_name=draft.state_name
            ).first()
            if exact and (exact.reply or "").strip():
                suggested_answer = exact.reply.strip()
            else:
                # 2) Semantic search from existing FAQ database (pgvector)
                # False-positive avoidance: require a configurable top similarity.
                try:
                    related = find_related_questions_scored(draft.subject, None, draft.memo_id, draft.state_name)
                    if related:
                        top = related[0]
                        top_sim = float(top.get("similarity") or 0.0)
                        # Tunable via env / config for easier calibration
                        suggest_threshold = float(current_app.config.get("SUGGESTION_SIMILARITY_THRESHOLD", 0.65))
                        min_margin = float(current_app.config.get("SUGGESTION_MIN_MARGIN", 0.02))
                        second_sim = float(related[1].get("similarity") or 0.0) if len(related) > 1 else 0.0
                        if top_sim >= suggest_threshold and (top_sim - second_sim) >= min_margin and top.get("reply"):
                            suggested_answer = top["reply"]
                except Exception as e:
                    current_app.logger.warning(f"Error finding related questions for draft {draft.id}: {e}")

            result.append({ 
                "id": draft.id, 
                "question": draft.subject,  # Use subject field as the question
                "state_name": draft.state_name, 
                "reply": draft.reply or "",
                "suggested_answer": suggested_answer or "",
                "created_at": draft.created_at.strftime('%Y-%m-%d') if draft.created_at else None
            })

        current_app.logger.info(f"Returning {len(result)} pending questions")
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error in get_pending_questions: {str(e)}")
        return jsonify({"error": "Failed to load pending questions", "details": str(e)}), 500


@pending_bp.route("/api/save_pending", methods=["POST"])
@login_required
def save_pending():
    user = current_user()
    role = get_role()
    # Viewers cannot save pending questions (read-only access)
    if role == 'viewer':
        return jsonify({"message": "Not authorized"}), 403

    data = request.get_json() or {}
    draft_id = data.get("id")
    reply = (data.get("reply") or "").strip()
    user_email = session.get('username') or session.get('email') or 'unknown'

    if not draft_id:
        return jsonify({"message": "Missing draft id."}), 400
    if not reply:
        return jsonify({"message": "Reply cannot be empty."}), 400

    draft = db.session.get(DraftFAQ, draft_id)

    if not draft:
        return jsonify({"message": "Draft not found."}), 404

    # modifier may only save drafts for their state
    if is_modifier() and draft.state_name != (user.state_name or ''):
        return jsonify({"message": "Not authorized to modify this draft."}), 403

    duplicate = DraftFAQ.query.filter(
        DraftFAQ.state_name == draft.state_name,
        DraftFAQ.norm_query == draft.norm_query, DraftFAQ.reply == reply,
        DraftFAQ.status == DraftStatus.admin_draft, DraftFAQ.id != draft.id
    ).first()

    if duplicate:
        return jsonify({"message": "This question with the same reply already exists."}), 409

    # Save reply and mark for admin review
    try:
        draft.reply = reply
        draft.status = DraftStatus.admin_draft
        draft.modified_by = user_email
        draft.modified_at = datetime.utcnow()
        draft.embedding = encode_text(draft.subject)
        db.session.commit()
        # After saving, if reply suggests future-fix, create tracker entry
        if detect_future_issue(reply):
            create_future_issue(
                #description=f"Question: {draft.subject}(Reply: {draft.reply})",
                description=f"Question: {draft.subject} \nReply: {draft.reply}",
                related_draft_id=draft.id,
                version_detected=os.getenv("PORTAL_VERSION", None)
            )
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed to save pending reply")
        return jsonify({"message": f"Failed to save reply: {str(e)}"}), 500

    add_log(f"{user_email} saved reply for draft ID {draft_id} (moved to admin drafts)", user_email)
    return jsonify({"message": "Reply saved and moved to admin drafts."}), 200


@pending_bp.route("/api/bulk_save", methods=["POST"])
@login_required
def bulk_save():
    """Save multiple draft replies at once"""
    user = current_user()
    role = get_role()
    
    # Only modifiers and admins can save drafts
    if role not in ['modifier', 'admin']:
        return jsonify({"message": "Not authorized for bulk save"}), 403
    
    data = request.get_json() or {}
    draft_data = data.get("drafts", [])
    user_email = session.get('username') or session.get('email') or 'unknown'
    
    if not draft_data:
        return jsonify({"message": "No draft data provided"}), 400
    
    successes = []
    failures = []
    
    for item in draft_data:
        draft_id = item.get("id")
        reply = (item.get("reply") or "").strip()
        
        if not draft_id or not reply:
            failures.append({"id": draft_id, "error": "Missing draft id or reply"})
            continue
        
        draft = db.session.get(DraftFAQ, draft_id)
        
        if not draft:
            failures.append({"id": draft_id, "error": "Draft not found"})
            continue
        
        # modifier may only save drafts for their state
        if is_modifier() and draft.state_name != (user.state_name or ''):
            failures.append({"id": draft_id, "error": "Not authorized to modify this draft"})
            continue
        
        duplicate = DraftFAQ.query.filter(
            DraftFAQ.state_name == draft.state_name,
            DraftFAQ.norm_query == draft.norm_query, DraftFAQ.reply == reply,
            DraftFAQ.status == DraftStatus.admin_draft, DraftFAQ.id != draft.id
        ).first()
        
        if duplicate:
            failures.append({"id": draft_id, "error": "This question with the same reply already exists"})
            continue
        
        try:
            draft.reply = reply
            draft.status = DraftStatus.admin_draft
            draft.modified_by = user_email
            draft.modified_at = datetime.utcnow()
            draft.embedding = encode_text(draft.subject)
            successes.append(draft_id)
            
            # After saving, if reply suggests future-fix, create tracker entry
            if detect_future_issue(reply):
                create_future_issue(
                    description=f"Question: {draft.subject} \nReply: {draft.reply}",
                    related_draft_id=draft.id,
                    version_detected=os.getenv("PORTAL_VERSION", None)
                )
        except Exception as e:
            db.session.rollback()
            failures.append({"id": draft_id, "error": f"Failed to save reply: {str(e)}"})
    
    if successes:
        try:
            db.session.commit()
            add_log(f"{user_email} performed bulk save on {len(successes)} drafts", user_email)
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Failed to commit changes: {str(e)}"}), 500
    
    return jsonify({
        "successes": len(successes),
        "failures": len(failures),
        "success_ids": successes,
        "failed_items": failures
    }), 200


@pending_bp.route("/api/delete_pending", methods=["POST"])
@login_required
def delete_pending():
    user = current_user()
    role = get_role()
    # Viewers cannot delete pending questions (read-only access)
    if role == 'viewer':
        return jsonify({"message": "Not authorized"}), 403
    
    data = request.get_json()
    qid = data.get("id")
    if not qid:
        return jsonify({"message": "Missing id"}), 400
    
    q = DraftFAQ.query.filter_by(id=qid).first()
    if not q:
        return jsonify({"message": "Not found"}), 404
    
    # Authorization: modifier can only delete their state's drafts
    if is_modifier() and q.state_name != (user.state_name or ''):
        return jsonify({"message": "Not authorized"}), 403
    
    db.session.delete(q)
    db.session.commit()
    return jsonify({"status": "ok", "message": "Deleted successfully"})
