from datetime import datetime
from flask import Blueprint, request, jsonify, session, flash, redirect, url_for
from flask_login import login_required

from app import db
from app.models import FutureIssueTracker, DraftFAQ, FAQ
from app.services.notification_service import NotificationService
from app.utils.embeddings import login_required, get_role, current_user

future_issues_bp = Blueprint("future_issues", __name__)


@future_issues_bp.route('/resolve-issue/<int:issue_id>', methods=['POST'])
@login_required
def resolve_future_issue(issue_id):
    """Resolve a future issue and notify users"""
    try:
        # Get current user info
        role = get_role()
        user_email = session.get('email')
        
        # Only admin and reviewer can resolve issues
        if role not in ['admin', 'reviewer']:
            return jsonify({'error': 'Access denied'}), 403
        
        # Get the future issue
        issue = FutureIssueTracker.query.get_or_404(issue_id)
        
        # Get resolution details from form
        version_fixed = request.form.get('version_fixed', '').strip()
        resolution_note = request.form.get('resolution_note', '').strip()
        new_reply = request.form.get('new_reply', '').strip()
        
        if not version_fixed:
            return jsonify({'error': 'Version fixed is required'}), 400
        
        # Update the issue
        issue.status = 'addressed'
        issue.version_fixed = version_fixed
        issue.note = resolution_note
        issue.resolution_date = datetime.utcnow()
        
        # Update related draft/FAQ with new reply if provided
        if new_reply:
            if issue.related_draft_id:
                draft = DraftFAQ.query.get(issue.related_draft_id)
                if draft:
                    draft.reply = new_reply
                    draft.modified_by = user_email
                    draft.modified_at = datetime.utcnow()
                    if draft.status.value == 'pending':
                        from app.models import DraftStatus
                        draft.status = DraftStatus.admin_draft
            
            elif issue.related_faq_id:
                faq = FAQ.query.get(issue.related_faq_id)
                if faq:
                    faq.reply = new_reply
                    # Update embedding for the reply
                    from app.utils.embeddings import set_embedding_for_model
                    set_embedding_for_model(faq, 'question')
        
        db.session.commit()
        
        # Create notifications
        notification_service = NotificationService()
        message = f"Future issue resolved in version {version_fixed}"
        if resolution_note:
            message += f": {resolution_note}"
        if new_reply:
            message += ". A new reply has been provided."
        
        notification_service.create_future_issue_notification(issue, message)
        
        flash('Future issue resolved successfully and notifications sent!', 'success')
        
        # Redirect back to the referring page
        next_page = request.form.get('next_page') or url_for('enhanced_frontend.enhanced_index')
        return redirect(next_page)
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error resolving future issue: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('enhanced_frontend.enhanced_index'))


@future_issues_bp.route('/api/future-issues', methods=['GET'])
@login_required
def get_future_issues():
    """Get list of future issues for the current user"""
    try:
        role = get_role()
        user_email = session.get('email')
        
        # Build query based on role
        query = FutureIssueTracker.query
        
        # Filter by status if requested
        status_filter = request.args.get('status')
        if status_filter:
            query = query.filter(FutureIssueTracker.status == status_filter)
        
        # Admin and reviewer can see all issues
        # Other roles see only issues related to their drafts
        if role not in ['admin', 'reviewer']:
            query = query.join(DraftFAQ).filter(DraftFAQ.created_by == user_email)
        
        issues = query.order_by(FutureIssueTracker.detected_at.desc()).all()
        
        # Format for JSON response
        result = []
        for issue in issues:
            issue_data = {
                'id': issue.id,
                'description': issue.description,
                'status': issue.status,
                'version_detected': issue.version_detected,
                'version_fixed': issue.version_fixed,
                'note': issue.note,
                'detected_at': issue.detected_at.isoformat() if issue.detected_at else None,
                'resolution_date': issue.resolution_date.isoformat() if issue.resolution_date else None
            }
            
            # Add related draft/FAQ info
            if issue.related_draft_id:
                draft = DraftFAQ.query.get(issue.related_draft_id)
                if draft:
                    issue_data['related_draft'] = {
                        'id': draft.id,
                        'subject': draft.subject,
                        'state': draft.state_name
                    }
            
            if issue.related_faq_id:
                faq = FAQ.query.get(issue.related_faq_id)
                if faq:
                    issue_data['related_faq'] = {
                        'id': faq.id,
                        'subject': faq.subject,
                        'state': faq.state_name
                    }
            
            result.append(issue_data)
        
        return jsonify({'issues': result})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
