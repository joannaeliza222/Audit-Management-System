import io
import os
import secrets
import pandas as pd
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, send_file, current_app
from openpyxl.workbook import Workbook
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models import User, db, FAQ, DraftFAQ, FutureIssueTracker, DraftStatus, DataDump
from app.utils.passwords import hash_password, verify_password
from app.utils.embeddings import (
    login_required,
    current_user,
    fetch_data,
    admin_required,
    allowed_file,
    sanitize_cell,
    normalize,
    normalize_text,
    get_bert_embeddings,
    get_bert_embeddings_batch,
    encode_text,
    create_future_issue,
    detect_future_issue,
)
from datetime import datetime, timedelta
from app.models import FailedLoginAttempt 
from app.utils.validation import validate_password 
from app.utils.validation import validate_file_mime, validate_file_size  # Add imports
import uuid



auth_bp = Blueprint("auth", __name__)

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@auth_bp.route('/login', methods=['GET', 'POST'])

def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        ip_address = request.remote_addr

        # Check for account lockout (5 failed attempts in last 15 minutes)
        recent_failures = FailedLoginAttempt.query.filter(
            FailedLoginAttempt.email == email,
            FailedLoginAttempt.attempt_time > datetime.utcnow() - timedelta(minutes=15),
            FailedLoginAttempt.success == False
        ).count()
        
        if recent_failures >= 5:
            flash("Account temporarily locked due to multiple failed attempts. Try again in 15 minutes.", "warning")
            # Log the attempt
            db.session.add(FailedLoginAttempt(
                email=email,
                ip_address=ip_address,
                success=False
            ))
            db.session.commit()
            return redirect(url_for('auth.login'))

        user = User.query.filter_by(email=email).first()
        if user:
            vr = verify_password(user.password, password)
        else:
            vr = None

        if user and vr and vr.ok:
            # Optional email verification gate (disabled by default; no email sender configured here)
            if current_app.config.get("REQUIRE_EMAIL_VERIFICATION", False) and not user.email_verified:
                flash("Email verification required. Please contact an administrator.", "warning")
                db.session.add(FailedLoginAttempt(email=email, ip_address=ip_address, success=False))
                db.session.commit()
                return redirect(url_for('auth.login'))
            
            if user.is_approved:
                # Log successful attempt
                db.session.add(FailedLoginAttempt(
                    email=email,
                    ip_address=ip_address,
                    success=True
                ))
                db.session.commit()
                
                
                session.permanent = True
                session.clear()
                session.permanent = True
                session['user_id'] = user.id
                session['role'] = (user.role or '').lower()
                session['username'] = user.email or user.name or ''

                # Opportunistic password hash upgrade to Argon2id
                try:
                    if vr.needs_rehash:
                        user.password = hash_password(password)
                        db.session.commit()
                except Exception:
                    db.session.rollback()
                return redirect(url_for('enhanced_frontend.enhanced_index'))
            else:
                db.session.add(FailedLoginAttempt(
                    email=email,
                    ip_address=ip_address,
                    success=False
                ))
                db.session.commit()
                flash("Awaiting admin approval", "warning")
                return redirect(url_for('auth.login'))
        else:
            # Log failed attempt
            db.session.add(FailedLoginAttempt(
                email=email,
                ip_address=ip_address,
                success=False
            ))
            db.session.commit()
            # Generic message to prevent user enumeration
            flash("Invalid credentials", "danger")
            return redirect(url_for('auth.login'))

    return render_template('login.html')



@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        requested_role = (request.form.get("role", "") or "").lower()
        name = (request.form.get("name", "") or "").strip()
        state = (request.form.get('state_name', '') or '').strip()

        if not email or not password:
            flash("Email and password are required", "warning")
            return redirect(url_for('auth.register'))

        # Validate password complexity
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg, "warning")
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            # Avoid user enumeration
            flash("If an account exists with that email, contact an administrator.", "info")
            return redirect(url_for('auth.login'))

        # Role assignment hardening:
        # - Never allow self-selecting privileged roles.
        # - Bootstrap: first registered user becomes admin + approved (single-developer / internal deploy).
        is_first_user = (User.query.count() == 0)
        role = "admin" if is_first_user else "viewer"

        hashed_pw = hash_password(password)
        new_user = User(
            name=name,
            email=email, 
            password=hashed_pw, 
            role=role, 
            state_name=state,
            email_verified=True,
            email_verification_token=None,
            is_approved=True if is_first_user else False,
        )

        db.session.add(new_user)
        db.session.commit()

        if is_first_user:
            flash("Admin account created. You can now log in.", "success")
        else:
            flash("Registered successfully. Awaiting admin approval.", "success")
        return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour")
def change_password():
    """
    Authenticated password change (avoids insecure/out-of-band reset flows).
    """
    user = current_user()
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        vr = verify_password(user.password, current_pw)
        if not vr.ok:
            flash("Current password is incorrect.", "danger")
            return redirect(url_for('auth.change_password'))

        if not new_pw or new_pw != confirm_pw:
            flash("New passwords do not match.", "warning")
            return redirect(url_for('auth.change_password'))

        is_valid, error_msg = validate_password(new_pw)
        if not is_valid:
            flash(error_msg, "warning")
            return redirect(url_for('auth.change_password'))

        try:
            user.password = hash_password(new_pw)
            # Clear any legacy reset fields if present
            user.password_reset_token = None
            user.password_reset_expires = None
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for('auth.index'))
        except Exception:
            db.session.rollback()
            flash("Failed to update password.", "danger")
            return redirect(url_for('auth.change_password'))

    return render_template('change_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('auth.login'))



@auth_bp.route('/index')
@login_required
def index():
    user = current_user()
    if not user:
        return redirect(url_for('auth.login'))
    role = (user.role or '').lower()
    try:
        records = DataDump.query.order_by(DataDump.id.desc()).all()
    except Exception:
        records = []

    distinct_states = [s[0] for s in (
        db.session.query(DraftFAQ.state_name)
        .filter(DraftFAQ.state_name.isnot(None))
        .filter(DraftFAQ.state_name != '')
        .filter(DraftFAQ.state_name != 'NaN')
        .filter(DraftFAQ.state_name != 'nan')
        .filter(DraftFAQ.state_name != 'None')
        .distinct().order_by(DraftFAQ.state_name.asc())
        .all()
    )]

    distinct_years = [y[0] for y in (
        db.session.query(db.extract('year', DataDump.request_date))
        .distinct()
        .order_by(db.extract('year', DataDump.request_date))
        .all()
    ) if y[0]]

    # distinct_years = [y[0] for y in (
    #     db.session.query(extract('year', DraftFAQ.created_at))
    #     .distinct().order_by(extract('year', DraftFAQ.created_at))
    #     .all()
    # ) if y[0]]

    total_states_count = len(distinct_states)
    total_dumps_count = DataDump.query.count()
    filtered_dumps_count = len(records)

    total_questions, total_states, unanswered_questions, state_wise_count = fetch_data()
    state_cards = [
        {
            "state": row[0],
            "total": row[1],
            "answered": row[2],
            "unanswered": row[3],
        } for row in state_wise_count]

    state_cards = sorted(state_cards, key=lambda x: x["state"].lower())

    # Calculate real-time statistics
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.audit_models import Commitment
    
    # Calculate AI accuracy based on actual FAQ quality
    total_faqs = FAQ.query.filter(FAQ.reply.isnot(None), FAQ.reply != '').count()
    high_quality_faqs = FAQ.query.filter(
        FAQ.reply.isnot(None), 
        FAQ.reply != '',
        func.length(FAQ.reply) > 50
    ).count()
    ai_accuracy = round((high_quality_faqs / total_faqs * 100) if total_faqs > 0 else 0, 1)
    
    # Calculate percentage changes (compare with last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # Pending queries change
    pending_queries_count = DraftFAQ.query.filter(
        (DraftFAQ.reply.is_(None) | (DraftFAQ.reply == '')),
        DraftFAQ.state_name.isnot(None),
        DraftFAQ.state_name != ''
    ).count()
    
    pending_last_month = DraftFAQ.query.filter(
        DraftFAQ.created_at >= thirty_days_ago,
        (DraftFAQ.reply.is_(None) | (DraftFAQ.reply == ''))
    ).count()
    pending_change_percent = round(((pending_queries_count - pending_last_month) / pending_last_month * 100) if pending_last_month > 0 else 0, 1)
    pending_change = f'+{pending_change_percent}%' if pending_change_percent >= 0 else f'{pending_change_percent}%'
    
    # Answered queries change
    answered_queries_count = FAQ.query.filter(
        FAQ.reply.isnot(None),
        FAQ.reply != '',
        FAQ.state_name.isnot(None),
        FAQ.state_name != ''
    ).count()
    
    answered_last_month = FAQ.query.filter(
        FAQ.timestamp >= thirty_days_ago,
        FAQ.reply.isnot(None),
        FAQ.reply != ''
    ).count()
    answered_change_percent = round(((answered_queries_count - answered_last_month) / answered_last_month * 100) if answered_last_month > 0 else 0, 1)
    answered_change = f'+{answered_change_percent}%' if answered_change_percent >= 0 else f'{answered_change_percent}%'
    
    # AI performance change
    recent_faqs = FAQ.query.filter(
        FAQ.timestamp >= thirty_days_ago,
        FAQ.reply.isnot(None),
        FAQ.reply != ''
    ).count()
    recent_high_quality = FAQ.query.filter(
        FAQ.timestamp >= thirty_days_ago,
        FAQ.reply.isnot(None),
        FAQ.reply != '',
        func.length(FAQ.reply) > 50
    ).count()
    recent_accuracy = round((recent_high_quality / recent_faqs * 100) if recent_faqs > 0 else 0, 1)
    ai_change_percent = round((ai_accuracy - recent_accuracy), 1)
    ai_change = f'+{ai_change_percent}%' if ai_change_percent >= 0 else f'{ai_change_percent}%'

    outstanding_issues = 0
    if session.get('role') == 'admin':
        outstanding_issues = FutureIssueTracker.query.filter_by(status='not addressed').count()


    # Enhanced frontend handles the root route now, so redirect to enhanced frontend
    return redirect(url_for('enhanced_frontend.enhanced_index'))



# -------------------------------
# Admin approvals & user control
# -------------------------------

@auth_bp.route("/admin/approvals", methods=["GET"])
@admin_required
def admin_approvals():
    user = db.session.get(User, session["user_id"])
    pending_users = User.query.filter_by(is_approved=False).all()

    return render_template(
        "index.html",
        user=user, pending_users=pending_users, role=session.get("role"),
        username=session.get("username"), page="userapproval"
    )


@auth_bp.route("/approve_user/<int:user_id>", methods=["POST"])
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    if not user.is_approved:
        # Require email verification before approval
        if not user.email_verified:
            flash(f"User '{user.email}' must verify their email before approval.", "warning")
            return redirect(url_for("auth.index") + "#userapproval")
        
        user.is_approved = True
        db.session.commit()
        flash(f"User '{user.email}' approved successfully!", "success")
    else:
        flash(f"User '{user.email}' is already approved.", "info")

    return redirect(url_for("auth.index") + "#userapproval")

TEMPLATE_SECRET = os.getenv("TEMPLATE_SECRET", secrets.token_urlsafe(32))

@auth_bp.route('/download-template')
def download_template():
    wb = Workbook()
    ws = wb.active
    # Column names match DraftFAQ model fields
    # Support both old 'question' and new 'subject' for backward compatibility
    ws.append(["subject", "query_description", "reply", "memo_id", "state_name"])

    wb.properties.comments = TEMPLATE_SECRET
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="faq_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@auth_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    """
    Saves rows into DraftFAQ with pgvector embeddings:
      - rows with reply -> status=admin_draft
      - rows without reply -> status=pending
    Skips duplicates safely.
    """
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('auth.index'))

    file = request.files['file']
    if not file or file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('auth.index'))

    filename = secure_filename(file.filename)
    if not allowed_file(filename):
        flash('Invalid file type', 'danger')
        return redirect(url_for('auth.index'))

    # Validate MIME type
    allowed_mimes = current_app.config.get('UPLOAD_ALLOWED_MIME_TYPES', set())
    is_valid_mime, mime_error = validate_file_mime(file, allowed_mimes)
    if not is_valid_mime:
        flash(mime_error or 'Invalid file type detected', 'danger')
        return redirect(url_for('auth.index'))

    # Validate file size
    max_size = current_app.config.get('MAX_CONTENT_LENGTH', 60 * 1024 * 1024 * 1024)
    is_valid_size, size_error = validate_file_size(file, max_size)
    if not is_valid_size:
        flash(size_error or 'File too large', 'danger')
        return redirect(url_for('auth.index'))

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    
    # Use UUID-based filename to prevent path traversal
    safe_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    filepath = os.path.join(upload_folder, safe_filename)
    file.save(filepath)

    try:
        # --- Load CSV or Excel ---
        ext = filename.rsplit('.', 1)[1].lower()
        if ext == 'csv':
            try:
                data = pd.read_csv(filepath, dtype=str)
            except UnicodeDecodeError:
                data = pd.read_csv(filepath, encoding='latin1', dtype=str)
        else:
            data = pd.read_excel(filepath, dtype=str)

        # Check if file is empty or has no data
        if data.empty or len(data) == 0:
            flash('The uploaded file is empty. Please fill in the data before uploading.', 'warning')
            return redirect(request.referrer or url_for('auth.index'))

        # Normalize columns
        data.columns = [c.lower().strip() for c in data.columns]
        
        # Debug: Log available columns
        current_app.logger.info(f"Upload file columns: {list(data.columns)}")
        
        # Support both old 'question' and new 'subject' column names
        if 'subject' in data.columns:
            question_col = 'subject'
        elif 'question' in data.columns:
            question_col = 'question'
        else:
            flash(f'File must contain "subject" or "question" column. Found columns: {list(data.columns)}', 'danger')
            return redirect(url_for('auth.index'))

        if 'state_name' not in data.columns:
            flash(f'File must contain "state_name" column. Found columns: {list(data.columns)}', 'danger')
            return redirect(url_for('auth.index'))

        current_app.logger.info(f"Processing {len(data)} rows from upload file")

        # Counters
        merged_pending = 0
        merged_review = 0
        duplicate_count = 0
        skipped_invalid = 0

        uploader = session.get('username') or session.get('email') or 'unknown'

        # Collect all valid rows first for batch processing
        valid_rows = []
        for idx, row in data.iterrows():
            try:
                # Get raw values first, handle NaN
                raw_question = row.get(question_col)
                raw_state_name = row.get('state_name')
                
                # Skip if truly None or NaN
                if pd.isna(raw_question) or pd.isna(raw_state_name):
                    skipped_invalid += 1
                    current_app.logger.debug(f"Row {idx}: Skipped due to NaN - question: {raw_question}, state: {raw_state_name}")
                    continue
                
                question = sanitize_cell(raw_question)
                query_description = sanitize_cell(row.get('query_description')) if 'query_description' in data.columns else ''
                state_name = sanitize_cell(raw_state_name)
                raw_reply = row.get('reply') if 'reply' in data.columns else None

                if raw_reply is None or pd.isna(raw_reply):
                    reply = None
                else:
                    reply = sanitize_cell(raw_reply)
                    if reply == "":
                        reply = None

                # Check if row has actual data (not just empty template)
                question_stripped = question.strip()
                state_name_stripped = state_name.strip()
                
                if not question_stripped or not state_name_stripped:
                    skipped_invalid += 1
                    current_app.logger.debug(f"Row {idx}: Skipped due to empty values - question: '{question}', state: '{state_name}'")
                    continue

                normq = normalize_text(question)

                # Check duplicate DraftFAQ based on subject + reply + state_name
                # Only consider duplicate if subject AND reply are the same from the same state
                exists = DraftFAQ.query.filter(
                    DraftFAQ.norm_query == normq,
                    DraftFAQ.reply == reply,
                    DraftFAQ.state_name == state_name
                ).first()

                if exists:
                    duplicate_count += 1
                    current_app.logger.debug(f"Row {idx}: Skipped duplicate (same subject, reply, and state) - {question}")
                    continue

                valid_rows.append({
                    'subject': question,
                    'query_description': query_description if query_description else question,
                    'normq': normq,
                    'reply': reply,
                    'memo_id': sanitize_cell(row.get('memo_id')) if 'memo_id' in data.columns and not pd.isna(row.get('memo_id')) else None,
                    'state_name': state_name
                })
            except Exception as e:
                skipped_invalid += 1
                current_app.logger.error(f"Row {idx}: Exception during processing - {str(e)}")
                continue

        current_app.logger.info(f"Validation complete: {len(valid_rows)} valid, {skipped_invalid} invalid, {duplicate_count} duplicates")

        # Check if no valid rows were found (empty template)
        if not valid_rows:
            if duplicate_count > 0:
                flash(f'All {duplicate_count} row(s) in the file are duplicates (same subject, reply, and state already exist). No new records added.', 'info')
            else:
                flash(f'The uploaded file has no valid data. Found {skipped_invalid} invalid row(s). Please ensure subject and state_name columns have data.', 'warning')
            return redirect(request.referrer or url_for('auth.index'))

        # Process embeddings in smaller batches to prevent hanging
        batch_size = current_app.config.get('EMBEDDING_BATCH_SIZE', 5)
        upload_max_rows = current_app.config.get('UPLOAD_MAX_ROWS', 50)
        
        if len(valid_rows) > upload_max_rows:
            flash(f"File too large. Maximum {upload_max_rows} rows allowed per upload.", 'warning')
            return redirect(url_for('auth.index'))
        
        questions_batch = [row['subject'] for row in valid_rows]
        
        # Process in smaller batches
        embeddings_batch = []
        for i in range(0, len(questions_batch), batch_size):
            batch_questions = questions_batch[i:i + batch_size]
            batch_embeddings = get_bert_embeddings_batch(batch_questions)
            embeddings_batch.extend(batch_embeddings)

        # -------- MAIN LOOP WITH BATCH EMBEDDINGS ----------
        for idx, row_data in enumerate(valid_rows):
            subject = row_data['subject']
            query_description = row_data['query_description']
            normq = row_data['normq']
            reply = row_data['reply']
            memo_id = row_data['memo_id']
            state_name = row_data['state_name']
            # Use upload time as query date
            query_date = datetime.utcnow().date()

            # Get pre-computed embedding from batch
            embedding_vec = embeddings_batch[idx]
            if embedding_vec is None:
                skipped_invalid += 1
                continue

            embedding_vec = normalize(embedding_vec)
            # Ensure embedding is a proper list of floats for pgvector
            try:
                if hasattr(embedding_vec, 'tolist'):
                    embedding_vec = embedding_vec.tolist()
                elif isinstance(embedding_vec, memoryview):
                    embedding_vec = embedding_vec.tobytes().decode('utf-8').split(',')
                    embedding_vec = [float(x.strip()) for x in embedding_vec if x.strip()]
                elif hasattr(embedding_vec, '__iter__') and not isinstance(embedding_vec, str):
                    embedding_vec = list(embedding_vec)
            except Exception as e:
                current_app.logger.error(f'Embedding conversion error: {e}')
                embedding_vec = []

            draft_entry = DraftFAQ(
                subject=subject,
                query_description=query_description,
                norm_query=normq,
                reply=reply or None,
                memo_id=memo_id,
                state_name=state_name,
                query_date=query_date,
                created_by=uploader,
                embedding=embedding_vec.tobytes() if hasattr(embedding_vec, 'tobytes') else encode_text(subject),
                status=DraftStatus.admin_draft if reply else DraftStatus.pending
            )

            db.session.add(draft_entry)

            try:
                db.session.commit()

                if reply:
                    merged_review += 1
                    # Optional future issue generation
                    if detect_future_issue(reply):
                        create_future_issue(
                            description=f"(Subject: {subject}), (Reply: {reply})",
                            related_draft_id=draft_entry.id,
                            version_detected=os.getenv("PORTAL_VERSION", None)
                        )
                else:
                    merged_pending += 1

            except IntegrityError:
                db.session.rollback()
                duplicate_count += 1
                continue

        flash(
            f"✅ File processed successfully. Added {merged_pending + merged_review} new record(s) ({merged_pending} pending, {merged_review} with reply). "
            f"Found {duplicate_count} duplicate(s) (same subject, reply, and state). {skipped_invalid} invalid row(s).",
            "success"
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Upload failure")
        flash(f"Failed to process file: {str(e)}", "danger")

    # Redirect to the page where the upload was initiated
    redirect_target = request.args.get('redirect') or request.referrer or url_for('auth.index')
    return redirect(redirect_target)
