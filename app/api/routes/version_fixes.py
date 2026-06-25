from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from app.utils.embeddings import login_required, current_user, get_role, is_admin, is_reviewer, is_modifier, detect_future_issue
from app.models import FutureIssueTracker, DraftFAQ, FAQ
from app import db
from datetime import datetime, timedelta
import os

version_fixes_bp = Blueprint('version_fixes', __name__)

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

@version_fixes_bp.route('/version-fixes', methods=['GET', 'POST'])
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
            return redirect(url_for('futurefix.future_issues'))
        return redirect(url_for('version_fixes.version_fixes'))
    
    # Handle POST requests for future issues status updates
    if request.method == 'POST':
        if not (is_admin() or is_reviewer()):
            flash("Not authorized to update issue status.", "warning")
            return redirect(url_for('version_fixes.version_fixes'))

        issue_id = request.form.get('issue_id')
        action = request.form.get('action', 'mark_addressed')
        note = request.form.get('note', '')
        version_fixed = request.form.get('version_fixed', None)

        issue = FutureIssueTracker.query.get(issue_id)
        if not issue:
            flash("Issue not found", "danger")
            return redirect(url_for('version_fixes.version_fixes'))

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

        return redirect(url_for('version_fixes.version_fixes'))

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

@version_fixes_bp.route('/api/version-fixes')
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
