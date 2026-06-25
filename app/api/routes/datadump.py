import os
from datetime import datetime
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, jsonify, current_app, send_file
from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename
from app.models import User, db, DataDump
from app.utils.embeddings import login_required, allowed_datadump_filename, save_datadump_file
from app.utils.datadump_utils import create_prefilled_doc, extract_filled_details, verify_signature


dump_bp = Blueprint("dump", __name__)


@dump_bp.route("/datadump", methods=["GET"])
@login_required
def datadump():
    user = db.session.get(User, session['user_id'])
    role = user.role

    # Filters
    selected_state = request.args.get('state', '').strip()
    selected_status = request.args.get('status', '').strip()
    selected_year = request.args.get('year', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    query = DataDump.query

    if role not in ['admin', 'reviewer']:
        query = query.filter(DataDump.state == user.state_name)

    if selected_state:
        query = query.filter(DataDump.state == selected_state)

    if selected_status:
        query = query.filter(DataDump.status == selected_status)

    if selected_year and selected_year.isdigit():
        query = query.filter(
            db.extract('year', DataDump.request_date) == int(selected_year)
        )

    if from_date:
        try:
            fd = datetime.strptime(from_date, "%Y-%m-%d").date()
            query = query.filter(DataDump.request_date >= fd)
        except Exception:
            pass
    if to_date:
        try:
            td = datetime.strptime(to_date, "%Y-%m-%d").date()
            query = query.filter(DataDump.request_date <= td)
        except Exception:
            pass

    records = query.order_by(DataDump.id.desc()).all()

    distinct_states = [s[0] for s in db.session.query(DataDump.state).distinct().order_by(DataDump.state).all()]
    distinct_years = [y[0] for y in db.session.query(db.extract('year', DataDump.request_date)).distinct().order_by(
        db.extract('year', DataDump.request_date)).all() if y[0]]

    total_dumps = DataDump.query.count()
    total_states = len(distinct_states)
    filtered_count = len(records)

    states = [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
        "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
        "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
        "Meghalaya", "Nagaland", "Odisha", "Punjab", "Rajasthan",
        "TN", "Telangana", "Uttar Pradesh", "West Bengal",
        "Uttarakhand", "Delhi"
    ]

    return render_template(
        "datadump.html",
        user=user,
        role=user.role,
        records=records,
        distinct_states=distinct_states,
        distinct_years=distinct_years,
        selected_state=selected_state,
        selected_year=selected_year,
        selected_status=selected_status,
        total_dumps=total_dumps,
        total_states_dump=total_states,
        filtered_dumps=filtered_count, states=states
    )


@dump_bp.route("/request_dump", methods=["POST"])
@login_required
def request_dump():
    try:
        user = db.session.get(User, session['user_id'])
        details = request.form.get("request_email")

        new_record = DataDump(
            state=request.form.get('state'),
            nodal_dept=request.form.get('nodal_dept'),
            coordinator=request.form.get('coordinator'),
            #request_date=datetime.utcnow().date(),
            request_date=request.form.get('request_date'),
            request_email=request.form.get('request_email'),
            status="REQUESTED"
        )
        db.session.add(new_record)
        db.session.commit()

        return jsonify(success=True)

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))


@dump_bp.route("/provide_dump/<int:record_id>", methods=["POST"])
@login_required
def provide_dump(record_id):
    try:
        user = db.session.get(User, session['user_id'])
        if user.role != 'admin':
            return jsonify(success=False, error="Unauthorized"), 403

        rec = db.session.get(DataDump, record_id)
        if not rec:
            return jsonify(success=False, error="Not found"), 404

        share_mode = request.form.get('share_mode')
        share_link = request.form.get('share_link')
        shared_to = request.form.get('shared_to')
        file_name = request.form.get('file_name')
        file_size = request.form.get('file_size')
        md5_hash = request.form.get('md5_hash')
        period_shared = request.form.get('period_shared')
        postgres_version = request.form.get('postgres_version')
        command_to_restore = request.form.get('command_to_restore')
        db_size = request.form.get('db_size')
        remarks = request.form.get('remarks')
        # file upload
        uploaded_file = request.files.get('file')

        if uploaded_file and uploaded_file.filename:
            if not allowed_datadump_filename(uploaded_file.filename):
                return jsonify(success=False, error="Invalid file type"), 400
            stored_name, stored_path = save_datadump_file(uploaded_file)
            rec.file_name = uploaded_file.filename
            rec.file_path = stored_name
            rec.is_file_available = True
            rec.generate_download_token()
            rec.share_mode = share_mode or 'Uploaded'
        else:
            # no file upload: may still include share_link (external link)
            rec.is_file_available = False
            rec.file_path = None
            # generate a token only if file exists; otherwise leave null
            rec.share_mode = share_mode or rec.share_mode
            rec.share_link = share_link or rec.share_link

        # set other metadata
        rec.share_date = datetime.utcnow().date()
        rec.shared_to = shared_to or rec.shared_to
        rec.file_size = file_size or rec.file_size
        rec.md5_hash = md5_hash or rec.md5_hash
        rec.period_shared = period_shared or rec.period_shared
        rec.postgres_version = postgres_version or rec.postgres_version
        rec.command_to_restore = command_to_restore or rec.command_to_restore
        rec.db_size = db_size or rec.db_size
        rec.remarks = remarks or rec.remarks

        rec.user_doc_downloaded = False
        rec.user_doc_signed = False
        rec.user_doc_verified = False
        rec.user_uploaded_doc = None

        generated_filename = create_prefilled_doc(rec)
        rec.generated_doc = generated_filename

        rec.status = "PROVIDED"

        db.session.commit()

        return jsonify(success=True, message="Datadump provided.")

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Datadump provide failed")
        return jsonify(success=False, error="Failed to provide datadump"), 500


@dump_bp.route('/download_datadump/<token>', methods=['GET'])
@login_required
def download_datadump(token):
    # find record by token
    rec = DataDump.query.filter_by(download_token=token, is_file_available=True).first()
    if not rec:
        abort(404)

    user = db.session.get(User, session['user_id'])

    # permissions: admin and reviewer can download any. Others only if same state or if provided a share_link.
    if user.role not in ['admin', 'reviewer']:
        if rec.state != (user.state_name or ''):
            # if external share_link exists and public, allow? For now block
            return jsonify(success=False, error="Not authorized to download this file."), 403

    # send file
    upload_folder = current_app.config['DATADUMP_UPLOAD_FOLDER']
    safe_name = rec.file_path
    file_full_path = os.path.join(upload_folder, safe_name)
    if not os.path.exists(file_full_path):
        abort(404)

    # stream file
    return send_file(file_full_path, as_attachment=True, download_name=rec.file_name)


@dump_bp.route("/reject_dump/<int:record_id>", methods=["POST"])
@login_required
def reject_dump(record_id):
    user = db.session.get(User, session['user_id'])

    if user.role != "admin":
        return jsonify(success=False, error="Unauthorized"), 403

    rec = db.session.get(DataDump, record_id)
    if not rec:
        return jsonify(success=False, error="Record not found"), 404

    remarks = request.form.get("remarks")
    rec.status = "REJECTED"
    rec.remarks = remarks or rec.remarks
    rec.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(success=True, message="Request Rejected.")



@dump_bp.route("/download_generated/<int:id>")
@login_required
def download_generated(id):
    rec = db.session.get(DataDump, id)
    if not rec or not rec.generated_doc:
        abort(404)

    folder = current_app.config['DATADUMP_GENERATED_FOLDER']
    path = os.path.join(folder, rec.generated_doc)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True)


@dump_bp.route("/mark_generated_downloaded/<int:id>", methods=["POST"])
@login_required
def mark_generated_downloaded(id):

    rec = db.session.get(DataDump, id)
    if not rec:
        return jsonify(success=False, error="Not found"), 404

    # Permission check: if needed, you can add role/state checks here.
    rec.user_doc_downloaded = True
    rec.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(success=True)


@dump_bp.route("/upload_completed/<int:id>", methods=["POST"])
@login_required
def upload_completed(id):
    rec = db.session.get(DataDump, id)
    if not rec:
        return jsonify(success=False, error="Not found"), 404

    if not rec.generated_doc:
        return jsonify(success=False, error="No generated document exists for this record."), 400

    if not rec.user_doc_downloaded:
        return jsonify(success=False,
                       error="Please download and sign the generated document before uploading."), 400

    uploaded = request.files.get("completed")
    if not uploaded or not uploaded.filename:
        return jsonify(success=False, error="No file provided"), 400

    filename = secure_filename(f"{id}__{datetime.utcnow().strftime('%Y%m%d%H%M%S')}__{uploaded.filename}")
    save_dir = current_app.config.get('USER_UPLOADED_FOLDER')
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)
    uploaded.save(save_path)

    # Verify signature
    try:
        is_signed = verify_signature(save_path)
    except Exception as e:
        # If verify_signature raises, treat as failure but return message
        return jsonify(success=False, error=f"Signature verification failed: {str(e)}"), 500

    if not is_signed:
        return jsonify(success=False, error="Uploaded file is not signed. Please sign the document and try again."), 400

    extracted = extract_filled_details(save_path)
    for field, value in extracted.items():
        if hasattr(rec, field) and value:
            setattr(rec, field, value)

    rec.user_uploaded_doc = filename
    rec.user_doc_signed = True
    rec.user_doc_verified = True
    rec.status = "ACKNOWLEDGED"
    rec.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(success=True, signed=True, message="Uploaded and acknowledged.")