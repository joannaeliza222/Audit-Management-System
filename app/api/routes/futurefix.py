import os
from datetime import datetime
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, jsonify
from app.models import User, db, FAQ, DraftFAQ, FutureIssueTracker
from app.utils.embeddings import login_required, current_user, get_role, \
     is_modifier, is_admin, is_reviewer, detect_future_issue

futurefix_bp = Blueprint("futurefix", __name__)


# -------------------------------
# Future Fixes page
# -------------------------------
@futurefix_bp.route('/admin/future_issues', methods=['GET', 'POST'])
@login_required
def future_issues():
    role = get_role()
    user = current_user()
    if role == 'viewer' or role is None:
        flash("Access denied: you are not permitted to view Future Issues.", "warning")
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        if not (is_admin() or is_reviewer()):
            flash("Not authorized to update issue status.", "warning")
            return redirect(url_for('futurefix.future_issues'))

        issue_id = request.form.get('issue_id')
        action = request.form.get('action', 'mark_addressed')
        note = request.form.get('note', '')
        version_fixed = request.form.get('version_fixed', None)

        issue = FutureIssueTracker.query.get(issue_id)
        if not issue:
            flash("Issue not found", "danger")
            return redirect(url_for('futurefix.future_issues'))

        if action == 'mark_addressed':
            issue.status = 'addressed'
            issue.version_fixed = version_fixed or os.getenv("PORTAL_VERSION", None)
            issue.resolution_date = datetime.utcnow()
            
            # Update note with timestamp
            if note:
                issue.note = (issue.note or '') + f"\n[marker:{datetime.utcnow().isoformat()}] {note}"
            
            # Update reply for related draft/FAQ if provided
            new_reply = request.form.get('new_reply', '').strip()
            if new_reply:
                if issue.related_draft_id:
                    draft = DraftFAQ.query.get(issue.related_draft_id)
                    if draft:
                        draft.reply = new_reply
                        draft.modified_at = datetime.utcnow()
                elif issue.related_faq_id:
                    faq = FAQ.query.get(issue.related_faq_id)
                    if faq:
                        faq.reply = new_reply

            db.session.commit()
            flash("Issue marked as addressed.", "success")
        elif action == 'mark_not_addressed':
            issue.status = 'not addressed'
            issue.version_fixed = None
            #issue.note = note
            if note:
                issue.note = (issue.note or '') + f"\n[marker:{datetime.utcnow().isoformat()}] {note}"

            db.session.commit()
            flash("Issue marked as not addressed.", "info")

        return redirect(url_for('futurefix.future_issues'))

    # Get future issues with filtering
    status_filter = request.args.get('status')
    query = FutureIssueTracker.query.order_by(FutureIssueTracker.detected_at.desc())
    if status_filter:
        query = query.filter(FutureIssueTracker.status == status_filter)

    issues = query.all()

    # Enrich issues with related data
    enriched_issues = []
    for idx, issue in enumerate(issues, start=1):
        issue_data = {
            'index': idx,
            'id': issue.id,
            'description': issue.description,
            'status': issue.status,
            'version_fixed': issue.version_fixed,
            'detected_at': issue.detected_at,
            'note': issue.note,
            'resolution_date': getattr(issue, 'resolution_date', None),
            'fulfilled': False
        }
        
        # Get subject from related draft or FAQ
        if issue.related_draft_id:
            draft = DraftFAQ.query.get(issue.related_draft_id)
            if draft:
                issue_data['subject'] = draft.subject
                issue_data['reply'] = draft.reply
                issue_data['state_name'] = draft.state_name
                # Check if fulfilled (reply contains future fix phrases)
                if draft.reply and detect_future_issue(draft.reply):
                    issue_data['fulfilled'] = True
                    issue_data['context'] = 'Will be addressed in future'
        
        elif issue.related_faq_id:
            faq = FAQ.query.get(issue.related_faq_id)
            if faq:
                issue_data['subject'] = faq.subject
                issue_data['reply'] = faq.reply
                issue_data['state_name'] = faq.state_name
                # Check if fulfilled (reply contains future fix phrases)
                if faq.reply and detect_future_issue(faq.reply):
                    issue_data['fulfilled'] = True
                    issue_data['context'] = 'Will be addressed in future'
        
        if 'subject' not in issue_data:
            issue_data['subject'] = issue.description
        
        enriched_issues.append(issue_data)

    if is_modifier():
        filtered = []
        for issue_data in enriched_issues:
            belongs = False
            if issue_data.get('state_name') == (user.state_name or ''):
                belongs = True
            if belongs:
                filtered.append(issue_data)
        enriched_issues = filtered

    can_mark_addressed = is_admin() or is_reviewer()

    return render_template('future_issues.html', issues=enriched_issues,
                           can_mark_addressed=can_mark_addressed,
                           role=session.get('role'))
