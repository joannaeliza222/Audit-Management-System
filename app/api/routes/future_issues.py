import os
from datetime import datetime, timedelta
from flask import Blueprint, request, session, redirect, render_template, url_for, flash, jsonify, current_app
from flask_login import login_required

from app import db
from app.models import FutureIssueTracker, DraftFAQ, FAQ
from app.services.notification_service import NotificationService
from app.utils.embeddings import login_required, current_user, get_role, \
     is_modifier, is_admin, is_reviewer, detect_future_issue

future_issues_bp = Blueprint("future_issues", __name__)


# -------------------------------
# Helper Functions
# -------------------------------

def scan_for_deferred_fixes():
    """
    Scan all DraftFAQ and FAQ records for deferred fix phrases and create FutureIssueTracker records
    """
    deferred_phrases = [
        'future fix', 'upcoming version', 'will be addressed', 'fixed in a future release',
        'will be fixed', 'to be addressed', 'scheduled for', 'planned for', 'in upcoming version',
        'future release', 'next version', 'later version', 'deferred', 'postponed'
    ]
    
    created_count = 0
    
    # Scan DraftFAQ records with replies
    drafts = DraftFAQ.query.filter(DraftFAQ.reply.isnot(None)).all()
    for draft in drafts:
        if detect_future_issue(draft.reply):
            # Check if already tracked
            existing = FutureIssueTracker.query.filter_by(
                related_draft_id=draft.id,
                status='not addressed'
            ).first()
            
            if not existing:
                issue = FutureIssueTracker(
                    related_draft_id=draft.id,
                    description=f"Deferred fix detected in draft: {draft.subject[:100]}...",
                    detected_at=datetime.utcnow(),
                    status='not addressed',
                    version_detected=os.getenv("PORTAL_VERSION", None)
                )
                db.session.add(issue)
                created_count += 1
    
    # Scan FAQ records
    faqs = FAQ.query.filter(FAQ.reply.isnot(None)).all()
    for faq in faqs:
        if detect_future_issue(faq.reply):
            # Check if already tracked
            existing = FutureIssueTracker.query.filter_by(
                related_faq_id=faq.id,
                status='not addressed'
            ).first()
            
            if not existing:
                issue = FutureIssueTracker(
                    related_faq_id=faq.id,
                    description=f"Deferred fix detected in FAQ: {faq.subject[:100]}...",
                    detected_at=datetime.utcnow(),
                    status='not addressed',
                    version_detected=os.getenv("PORTAL_VERSION", None)
                )
                db.session.add(issue)
                created_count += 1
    
    if created_count > 0:
        db.session.commit()
        current_app.logger.info(f"Created {created_count} FutureIssueTracker records from scan")
    
    return created_count


# -------------------------------
# Main UI Page - Future Issues
# -------------------------------

@future_issues_bp.route('/admin/future_issues', methods=['GET', 'POST'])
@login_required
def future_issues():
    """Main future issues page with filtering and status updates"""
    role = get_role()
    user = current_user()
    
    # Allow viewers to view in read-only mode
    can_mark_addressed = is_admin() or is_reviewer()

    if request.method == 'POST':
        # Only allow admins and reviewers to update issues
        if not (is_admin() or is_reviewer()):
            flash("Not authorized to update issue status.", "warning")
            return redirect(url_for('future_issues.future_issues'))

        issue_id = request.form.get('issue_id')
        action = request.form.get('action', 'mark_addressed')
        note = request.form.get('note', '')
        version_fixed = request.form.get('version_fixed', None)

        issue = FutureIssueTracker.query.get(issue_id)
        if not issue:
            flash("Issue not found", "danger")
            return redirect(url_for('future_issues.future_issues'))

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
            if note:
                issue.note = (issue.note or '') + f"\n[marker:{datetime.utcnow().isoformat()}] {note}"

            db.session.commit()
            flash("Issue marked as not addressed.", "info")

        return redirect(url_for('future_issues.future_issues'))

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


# -------------------------------
# Version Fixes Dashboard
# -------------------------------

@future_issues_bp.route('/version-fixes', methods=['GET', 'POST'])
@login_required
def version_fixes():
    """Upcoming version fixes dashboard with future issues integration"""
    
    role = get_role()
    user = current_user()
    
    # Scan for deferred fixes when explicitly requested
    scan_param = request.args.get('scan')
    redirect_target = request.args.get('redirect', 'version_fixes')
    if scan_param == 'true' and (is_admin() or is_reviewer()):
        created = scan_for_deferred_fixes()
        if created > 0:
            flash(f"Scanned for deferred fixes. Created {created} new issue(s).", "success")
        else:
            flash("No new deferred fixes found.", "info")
        if redirect_target == 'future_issues':
            return redirect(url_for('future_issues.future_issues'))
        return redirect(url_for('future_issues.version_fixes'))
    
    # Handle POST requests for future issues status updates
    if request.method == 'POST':
        if not (is_admin() or is_reviewer()):
            flash("Not authorized to update issue status.", "warning")
            return redirect(url_for('future_issues.version_fixes'))

        issue_id = request.form.get('issue_id')
        action = request.form.get('action', 'mark_addressed')
        note = request.form.get('note', '')
        version_fixed = request.form.get('version_fixed', None)

        issue = FutureIssueTracker.query.get(issue_id)
        if not issue:
            flash("Issue not found", "danger")
            return redirect(url_for('future_issues.version_fixes'))

        if action == 'mark_addressed':
            issue.status = 'addressed'
            issue.version_fixed = version_fixed or os.getenv("PORTAL_VERSION", None)
            if note:
                issue.note = (issue.note or '') + f"\n[marker:{datetime.utcnow().isoformat()}] {note}"
            db.session.commit()
            flash("Issue marked as addressed.", "success")
        elif action == 'mark_not_addressed':
            issue.status = 'not addressed'
            issue.version_fixed = None
            if note:
                issue.note = (issue.note or '') + f"\n[marker:{datetime.utcnow().isoformat()}] {note}"
            db.session.commit()
            flash("Issue marked as not addressed.", "info")

        return redirect(url_for('future_issues.version_fixes'))

    # Get future issues with filtering
    status_filter = request.args.get('status')
    query = FutureIssueTracker.query.order_by(FutureIssueTracker.detected_at.desc())
    if status_filter:
        query = query.filter(FutureIssueTracker.status == status_filter)

    future_issues = query.all()
    
    # Filter issues for modifier role
    if is_modifier():
        filtered = []
        for issue in future_issues:
            belongs = False
            if issue.related_draft_id:
                d = DraftFAQ.query.get(issue.related_draft_id)
                if d and d.state_name == (user.state_name or ''):
                    belongs = True
            if issue.related_faq_id:
                f = FAQ.query.get(issue.related_faq_id)
                if f and f.state_name == (user.state_name or ''):
                    belongs = True
            if belongs:
                filtered.append(issue)
        future_issues = filtered

    can_mark_addressed = is_admin() or is_reviewer()
    
    # Convert FutureIssueTracker records to upcoming_fixes format
    upcoming_fixes = []
    for issue in future_issues:
        # Get related content
        subject = ""
        if issue.related_draft_id:
            draft = DraftFAQ.query.get(issue.related_draft_id)
            if draft:
                subject = draft.subject
        elif issue.related_faq_id:
            faq = FAQ.query.get(issue.related_faq_id)
            if faq:
                subject = faq.subject
        
        # Map status
        status_map = {
            'not addressed': 'pending',
            'addressed': 'completed'
        }
        status = status_map.get(issue.status, 'pending')
        
        # Determine priority based on detection
        priority = 'medium'
        if 'urgent' in issue.description.lower() or 'critical' in issue.description.lower():
            priority = 'high'
        elif 'low' in issue.description.lower():
            priority = 'low'
        
        upcoming_fixes.append({
            'id': issue.id,
            'title': subject[:100] if subject else 'Deferred Fix',
            'description': issue.description,
            'priority': priority,
            'status': status,
            'target_version': issue.version_fixed or 'TBD',
            'assigned_to': 'Development Team',
            'created_date': issue.detected_at,
            'target_date': issue.detected_at + timedelta(days=30) if status == 'pending' else issue.detected_at,
            'progress': 0 if status == 'pending' else 100,
            'affected_modules': [],
            'issue_type': 'deferred_fix',
            'dependencies': []
        })
    
    # Calculate statistics
    total_fixes = len(upcoming_fixes)
    completed_fixes = len([f for f in upcoming_fixes if f['status'] == 'completed'])
    in_progress_fixes = 0  # No in_progress status in FutureIssueTracker
    overdue_fixes = len([f for f in upcoming_fixes if f['target_date'] < datetime.now() and f['status'] != 'completed'])
    
    # Group by priority
    priority_counts = {
        'high': len([f for f in upcoming_fixes if f['priority'] == 'high']),
        'medium': len([f for f in upcoming_fixes if f['priority'] == 'medium']),
        'low': len([f for f in upcoming_fixes if f['priority'] == 'low'])
    }
    
    # Group by status
    status_counts = {
        'completed': completed_fixes,
        'in_progress': in_progress_fixes,
        'pending': len([f for f in upcoming_fixes if f['status'] == 'pending'])
    }
    
    return render_template('version_fixes.html',
                         user=current_user(),
                         role=role,
                         upcoming_fixes=upcoming_fixes,
                         future_issues=future_issues,
                         total_fixes=total_fixes,
                         completed_fixes=completed_fixes,
                         in_progress_fixes=in_progress_fixes,
                         overdue_fixes=overdue_fixes,
                         priority_counts=priority_counts,
                         status_counts=status_counts,
                         can_mark_addressed=can_mark_addressed,
                         status_filter=status_filter)


# -------------------------------
# API Endpoints
# -------------------------------

@future_issues_bp.route('/api/version-fixes')
@login_required
def api_version_fixes():
    """API endpoint for version fixes data"""
    
    # Get future issues from database
    status_filter = request.args.get('status')
    query = FutureIssueTracker.query.order_by(FutureIssueTracker.detected_at.desc())
    if status_filter:
        query = query.filter(FutureIssueTracker.status == status_filter)
    
    future_issues = query.all()
    
    # Convert to API format
    upcoming_fixes = []
    for issue in future_issues:
        # Get related content
        subject = ""
        if issue.related_draft_id:
            draft = DraftFAQ.query.get(issue.related_draft_id)
            if draft:
                subject = draft.subject
        elif issue.related_faq_id:
            faq = FAQ.query.get(issue.related_faq_id)
            if faq:
                subject = faq.subject
        
        # Map status
        status_map = {
            'not addressed': 'pending',
            'addressed': 'completed'
        }
        status = status_map.get(issue.status, 'pending')
        
        # Determine priority based on detection
        priority = 'medium'
        if 'urgent' in issue.description.lower() or 'critical' in issue.description.lower():
            priority = 'high'
        elif 'low' in issue.description.lower():
            priority = 'low'
        
        upcoming_fixes.append({
            'id': issue.id,
            'title': subject[:100] if subject else 'Deferred Fix',
            'description': issue.description,
            'priority': priority,
            'status': status,
            'target_version': issue.version_fixed or 'TBD',
            'assigned_to': 'Development Team',
            'created_date': issue.detected_at.isoformat() if issue.detected_at else None,
            'target_date': (issue.detected_at + timedelta(days=30)).isoformat() if issue.detected_at and status == 'pending' else (issue.detected_at.isoformat() if issue.detected_at else None),
            'progress': 0 if status == 'pending' else 100,
            'affected_modules': [],
            'issue_type': 'deferred_fix',
            'dependencies': []
        })
    
    return jsonify({
        'success': True,
        'fixes': upcoming_fixes,
        'total': len(upcoming_fixes),
        'completed': len([f for f in upcoming_fixes if f['status'] == 'completed']),
        'in_progress': 0,
        'overdue': len([f for f in upcoming_fixes if f['target_date'] and datetime.fromisoformat(f['target_date']) < datetime.now() and f['status'] != 'completed'])
    })


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
