import os
from datetime import datetime
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, jsonify, current_app
from sqlalchemy import extract

from app.models import db, FAQ, DraftFAQ, DraftStatus
from app.utils.embeddings import login_required, normalize_text, \
    detect_future_issue, create_future_issue, get_role, current_user, set_embedding_for_model, is_admin, is_modifier, \
    get_bert_embeddings, is_reviewer, add_log, normalize, encode_text
from app.utils.vector_support import serialize_vector
from app import csrf

review_bp = Blueprint("review", __name__)


# -------------------------------
# Review drafts / admin page
# -------------------------------
@review_bp.route('/review_drafts', methods=['GET', 'POST'])
@login_required
def review_drafts():
    role = get_role()
    user = current_user()
    email = session.get('email')

    # Review page is visible only to Admin and Reviewer
    if role not in ['admin', 'reviewer']:
        flash("Access denied: you are not permitted to view the Review page.", "warning")
        return redirect(url_for('index'))

    if request.method == 'POST':
        draft_id = request.form.get('draft_id')
        action = request.form.get('action')
        if draft_id and action:
            draft = DraftFAQ.query.get(int(draft_id))
            if not draft:
                flash("Draft not found", "danger")
                return redirect(url_for('review.review_drafts'))

            if action == 'merge':
                if not is_admin():
                    flash("Merge allowed for admin only.", "warning")
                    return redirect(url_for('review.review_drafts'))

                # Check duplicates before merging
                existing = FAQ.query.filter_by(norm_query=draft.norm_query,
                                               state_name=draft.state_name).first()
                if existing:
                    flash(f"Duplicate found: {draft.subject}", "warning")

                else:
                    faq_entry = FAQ(
                        subject=draft.subject, norm_query=draft.norm_query,
                        reply=draft.reply, memo_id=draft.memo_id, state_name=draft.state_name
                    )

                    set_embedding_for_model(faq_entry, 'subject')
                    db.session.add(faq_entry)
                    db.session.flush()
                    draft.original_id = faq_entry.id

                # mark draft merged, but keep it for history
                draft.status = DraftStatus.merged
                draft.approved_at = datetime.utcnow()
                draft.approved_by = email
                db.session.commit()

                # If the reply contains future-issue phrase, create tracker
                if detect_future_issue(draft.reply or ''):
                    create_future_issue(
                        description=f"Detected 'future release' mention for question: {draft.subject}",
                        related_faq_id=draft.original_id,
                        version_detected=os.getenv("PORTAL_VERSION", None)
                    )

                flash(f"Merged '{draft.subject}' successfully.", "success")
                add_log(f"Admin {email} merged draft ID {draft_id}", email)

            elif action == 'delete':
                # Review page: only Admin and Reviewer can delete
                if role in ['admin', 'reviewer']:
                    db.session.delete(draft)
                    db.session.commit()
                    flash("Draft deleted successfully", "info")
                else:
                    flash("You are not authorized to delete this draft.", "warning")

            elif action == 'update':
                # Review page: only Admin and Reviewer can update
                if role in ['admin', 'reviewer']:
                    reply_text = request.form.get('reply', '').strip()
                    draft.reply = reply_text or draft.reply
                    draft.modified_by = email
                    draft.modified_at = datetime.utcnow()
                    # if someone adds reply, promote to admin_draft
                    if draft.reply:
                        draft.status = DraftStatus.admin_draft
                    set_embedding_for_model(draft, 'question')
                    db.session.commit()
                    flash("Draft updated successfully", "success")
                else:
                    flash("You are not authorized to update this draft.", "warning")

        return redirect(url_for('review.review_drafts'))

    selected_year = request.args.get('year', type=int)
    selected_state = request.args.get('state')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    # query = DraftFAQ.query
    query = DraftFAQ.query.filter(
        DraftFAQ.status != DraftStatus.merged,
        DraftFAQ.reply.isnot(None),
        DraftFAQ.reply != '',
        DraftFAQ.state_name.isnot(None),
        DraftFAQ.state_name != ''
    )

    if selected_year:
        query = query.filter(extract('year', DraftFAQ.created_at) == selected_year)
    if selected_state:
        query = query.filter(DraftFAQ.state_name == selected_state)
    if from_date and to_date:
        query = query.filter(DraftFAQ.created_at.between(from_date, to_date))

    # Admin and Reviewer can see all drafts from all states
    # No state filtering needed since only Admin and Reviewer can access this page

    drafts = query.order_by(DraftFAQ.created_at.desc()).all()


    distinct_years = [y[0] for y in db.session.query(extract('year', DraftFAQ.created_at)).distinct().all()]
    distinct_states = [s[0] for s in db.session.query(DraftFAQ.state_name).filter(
        DraftFAQ.state_name.isnot(None),
        DraftFAQ.state_name != '',
        DraftFAQ.state_name != 'NaN',
        DraftFAQ.state_name != 'nan',
        DraftFAQ.state_name != 'None'
    ).distinct().all() if s[0]]
    distinct_states = sorted(distinct_states)

    return render_template(
        'admin_drafts.html',
        drafts=drafts, distinct_years=distinct_years,
        distinct_states=distinct_states, selected_year=selected_year,
        selected_state=selected_state, from_date=from_date, to_date=to_date,

    )


@review_bp.route("/api/merge_draft", methods=["POST"])
@csrf.exempt
@login_required
def merge_draft():
    if not is_admin():
        return jsonify({"message": "Not authorized to merge."}), 403

    data = request.get_json()
    draft_id = data.get("id")
    new_reply = (data.get("reply") or "").strip()

    user_email = session.get("username") or session.get("email") or "unknown"

    if not draft_id:
        return jsonify({"message": "Missing draft id."}), 400

    draft = db.session.get(DraftFAQ, draft_id)
    if not draft:
        return jsonify({"message": "Draft not found."}), 404

    try:
        state = (draft.state_name or "").strip()

        norm_q = draft.norm_query or normalize_text(draft.subject)

        # Check if FAQ already exists for normalized question + state
        existing = FAQ.query.filter_by(
            norm_query=norm_q,
            state_name=state
        ).first()

        if existing:
            # Merge behavior: update reply + timestamp
            existing.reply = new_reply or draft.reply or existing.reply
            existing.timestamp = datetime.utcnow()
            draft.original_id = existing.id

            # Ensure embedding exists for pgvector
            if existing.embedding is None:
                existing.embedding = get_bert_embeddings(existing.subject)

        else:
            # Create new FAQ
            new_faq = FAQ(
                subject=draft.subject,
                norm_query=norm_q,
                reply=new_reply or draft.reply,
                memo_id=draft.memo_id,
                state_name=state,
                embedding=get_bert_embeddings(draft.subject)  # pgvector stored directly
            )

            db.session.add(new_faq)
            db.session.flush()   # Get new_faq.id without commit
            draft.original_id = new_faq.id

        # Future Issue Detector
        final_reply = new_reply or draft.reply or ""
        if detect_future_issue(final_reply):
            create_future_issue(
                description=f"Question: {final_reply}",
                related_faq_id=draft.original_id,
                version_detected=os.getenv("PORTAL_VERSION"),
            )

        # Update draft details
        draft.status = DraftStatus.merged
        draft.approved_by = user_email
        draft.approved_at = datetime.utcnow()

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed merging draft")
        return jsonify({"message": f"Failed merging draft: {str(e)}"}), 500

    add_log(f"{user_email} merged draft ID {draft_id} into FAQ", user_email)
    return jsonify({"message": "Draft successfully merged into FAQ."})


@review_bp.route("/api/bulk_merge", methods=["POST"])
@login_required
def bulk_merge():
    if not is_admin():
        return jsonify({"message": "Not authorized for bulk merge"}), 403

    data = request.get_json() or {}
    ids = data.get("ids", [])

    if not isinstance(ids, list) or not ids:
        return jsonify({"message": "Missing draft id list"}), 400

    results = {"merged": [], "skipped": []}

    try:
        # Use bytea serialization for vector storage
        pgvector_available = True  # We'll use bytea with application-level vector support

        drafts = (
            db.session.query(DraftFAQ)
            .filter(DraftFAQ.id.in_(ids))
            .all()
        )

        if not drafts:
            return jsonify({"message": "No valid drafts found"}), 404

        existing_by_key = {}
        new_faq_objects = []

        for draft in drafts:
            key = (draft.norm_query, draft.state_name)

            if key not in existing_by_key:
                existing_by_key[key] = (
                    FAQ.query.filter_by(
                        norm_query=draft.norm_query,
                        state_name=draft.state_name
                    ).first()
                )

            existing_faq = existing_by_key[key]

            if existing_faq:
                # Update existing FAQ
                existing_faq.reply = draft.reply or existing_faq.reply
                existing_faq.timestamp = datetime.utcnow()
                draft.original_id = existing_faq.id

            else:
                # Create new FAQ entry
                new_faq = FAQ(
                    subject=draft.subject,
                    norm_query=draft.norm_query,
                    reply=draft.reply,
                    memo_id=draft.memo_id,
                    state_name=draft.state_name
                )
                # Generate and serialize embedding
                try:
                    embedding = get_bert_embeddings(draft.subject)
                    if embedding is not None:
                        normalized_embedding = normalize(embedding) if hasattr(embedding, 'tolist') else embedding
                        new_faq.embedding = serialize_vector(normalized_embedding)
                    else:
                        new_faq.embedding = None
                except Exception as e:
                    current_app.logger.error(f"Error generating embedding for FAQ ID {draft.id}: {e}")
                    new_faq.embedding = None
                    
                new_faq_objects.append(new_faq)

                # Track mapping
                existing_by_key[key] = new_faq
                draft.original_id = None

            draft.status = DraftStatus.merged
            draft.approved_at = datetime.utcnow()
            draft.approved_by = session.get("email") or session.get("username")
            results["merged"].append(draft.id)

        # Add new FAQs together
        if new_faq_objects:
            db.session.add_all(new_faq_objects)
            db.session.flush()  # assigns IDs

            # Generate and serialize embeddings for all new FAQs
            for faq in new_faq_objects:
                if faq.embedding is None:  # Only try to generate for None embeddings
                    try:
                        embedding = get_bert_embeddings(faq.subject)
                        if embedding is not None:
                            normalized_embedding = normalize(embedding) if hasattr(embedding, 'tolist') else embedding
                            faq.embedding = serialize_vector(normalized_embedding)
                        else:
                            faq.embedding = None
                    except Exception as e:
                        current_app.logger.error(f"Error generating embedding for FAQ ID {faq.id}: {e}")
                        faq.embedding = None

        # Commit all changes
        db.session.commit()
        
        current_app.logger.info(f"Bulk merge completed: {len(results['merged'])} merged, {len(results['skipped'])} skipped")

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Bulk merge failed")
        return jsonify({"message": f"Bulk merge failed: {str(e)}"}), 500

    return jsonify(results), 200


@review_bp.route("/api/delete_draft", methods=["POST"])
@csrf.exempt
@login_required
def delete_draft():
    data = request.get_json()
    draft_id = data.get("id")
    if not draft_id:
        return jsonify({"success": False, "message": "Missing draft id."}), 400

    draft = db.session.get(DraftFAQ, draft_id)
    if not draft:
        return jsonify({"success": False, "message": "Draft not found."}), 404

    user = current_user()
    role = get_role()

    # Review page functionality: only Admin and Reviewer can delete drafts
    if role not in ['admin', 'reviewer']:
        return jsonify({"success": False, "message": "Not authorized to delete draft."}), 403

    try:
        db.session.delete(draft)
        db.session.commit()
        add_log(f"{session.get('username')} deleted admin draft ID {draft_id}", session.get('username'))
        return jsonify({"success": True, "message": "Draft deleted successfully."}), 200

    except Exception as e:
        db.session.rollback()
        app.logger.exception("Error deleting draft")
        return jsonify({"success": False, "message": f"Error deleting draft: {str(e)}"}), 500


@review_bp.route("/api/save_pending", methods=["POST"])
@csrf.exempt
@login_required
def save_pending_review():
    """Save draft reply from review page"""
    user = current_user()
    role = get_role()
    
    # Only admin and reviewer can save drafts on review page
    if role not in ['admin', 'reviewer']:
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

    # Save reply and keep as admin_draft
    try:
        draft.reply = reply
        draft.status = DraftStatus.admin_draft
        draft.modified_by = user_email
        draft.modified_at = datetime.utcnow()
        draft.embedding = encode_text(draft.subject)
        db.session.commit()
        
        # If the reply contains future-issue phrase, create tracker
        if detect_future_issue(reply):
            create_future_issue(
                description=f"Question: {draft.subject} \nReply: {draft.reply}",
                related_draft_id=draft.id,
                version_detected=os.getenv("PORTAL_VERSION", None)
            )
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed to save draft reply")
        return jsonify({"message": f"Failed to save reply: {str(e)}"}), 500

    add_log(f"{user_email} saved reply for draft ID {draft_id} on review page", user_email)
    return jsonify({"message": "Reply saved successfully."}), 200


@review_bp.route("/api/bulk_save", methods=["POST"])
@login_required
def bulk_save_review():
    """Bulk save draft replies from review page"""
    user = current_user()
    role = get_role()
    
    # Only admin and reviewer can save drafts on review page
    if role not in ['admin', 'reviewer']:
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
        
        try:
            draft.reply = reply
            draft.status = DraftStatus.admin_draft
            draft.modified_by = user_email
            draft.modified_at = datetime.utcnow()
            draft.embedding = encode_text(draft.subject)
            successes.append(draft_id)
            
            # If the reply contains future-issue phrase, create tracker
            if detect_future_issue(reply):
                create_future_issue(
                    description=f"Question: {draft.subject} \nReply: {draft.reply}",
                    related_draft_id=draft.id,
                    version_detected=os.getenv("PORTAL_VERSION", None)
                )
        except Exception as e:
            failures.append({"id": draft_id, "error": f"Failed to save reply: {str(e)}"})
    
    if successes:
        try:
            db.session.commit()
            add_log(f"{user_email} performed bulk save on {len(successes)} drafts on review page", user_email)
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Failed to commit changes: {str(e)}"}), 500
    
    return jsonify({
        "successes": len(successes),
        "failures": len(failures),
        "success_ids": successes,
        "failed_items": failures
    }), 200


@review_bp.route("/api/bulk_delete", methods=["POST"])
@csrf.exempt
@login_required
def bulk_delete():
    if not is_admin():
        return jsonify({"message": "Not authorized for bulk delete"}), 403
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return jsonify({"message": "Missing id list"}), 400

    results = {"deleted": [], "skipped": []}
    try:
        for draft_id in ids:
            draft = db.session.get(DraftFAQ, draft_id)
            if not draft:
                results["skipped"].append({"id": draft_id, "reason": "not found"})
                continue
            db.session.delete(draft)
            results["deleted"].append(draft_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Bulk delete failed")
        return jsonify({"message": f"Bulk delete failed: {str(e)}"}), 500

    return jsonify(results), 200
