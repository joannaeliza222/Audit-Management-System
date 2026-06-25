from flask import Blueprint, render_template, jsonify, request, g, session
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_

from app import db
from app.audit_models import AuditQuery, Commitment, CommitmentStatus, AuditQueryStatus
from app.services.commitment_tracker import CommitmentTracker
from app.services.notification_service import NotificationService
from app.utils.embeddings import login_required, current_user

commitment_dashboard_bp = Blueprint('commitment_dashboard', __name__, url_prefix='/api/commitments')


@commitment_dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """Main commitment dashboard with widgets"""
    return render_template('commitment_dashboard.html')


@commitment_dashboard_bp.route('/dashboard/data')
@login_required
def dashboard_data():
    """Get dashboard data as JSON"""
    try:
        commitment_tracker = CommitmentTracker()
        
        # Get basic statistics
        dashboard_data = commitment_tracker.get_commitment_dashboard_data()
        
        # Get recent activity
        recent_activity = get_recent_commitment_activity()
        
        # Get commitment trends
        trends = get_commitment_trends()
        
        # Get critical issues
        critical_issues = dashboard_data.get('critical_issues', [])
        
        return jsonify({
            'status': 'success',
            'data': {
                'statistics': dashboard_data,
                'recent_activity': recent_activity,
                'trends': trends,
                'critical_issues': critical_issues,
                'last_updated': datetime.utcnow().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@commitment_dashboard_bp.route('/overdue')
@login_required
def overdue_commitments():
    """Get overdue commitments"""
    try:
        commitment_tracker = CommitmentTracker()
        overdue = commitment_tracker.get_overdue_commitments()
        
        commitments_data = []
        for commitment in overdue:
            commitments_data.append({
                'id': commitment.id,
                'query_id': commitment.audit_query.query_id if commitment.audit_query else 'N/A',
                'state': commitment.audit_query.state_name if commitment.audit_query else 'N/A',
                'commitment_text': commitment.commitment_text,
                'target_date': commitment.target_date.isoformat() if commitment.target_date else None,
                'days_overdue': (datetime.now().date() - commitment.target_date).days,
                'status': commitment.status.value,
                'priority': commitment.audit_query.priority if commitment.audit_query else 'medium'
            })
        
        return jsonify({
            'status': 'success',
            'data': commitments_data,
            'count': len(commitments_data)
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@commitment_dashboard_bp.route('/upcoming')
@login_required
def upcoming_commitments():
    """Get upcoming commitments"""
    try:
        days_ahead = request.args.get('days', 7, type=int)
        commitment_tracker = CommitmentTracker()
        upcoming = commitment_tracker.get_upcoming_commitments(days_ahead)
        
        commitments_data = []
        for commitment in upcoming:
            commitments_data.append({
                'id': commitment.id,
                'query_id': commitment.audit_query.query_id if commitment.audit_query else 'N/A',
                'state': commitment.audit_query.state_name if commitment.audit_query else 'N/A',
                'commitment_text': commitment.commitment_text,
                'target_date': commitment.target_date.isoformat() if commitment.target_date else None,
                'days_until_due': (commitment.target_date - datetime.now().date()).days,
                'status': commitment.status.value,
                'priority': commitment.audit_query.priority if commitment.audit_query else 'medium'
            })
        
        return jsonify({
            'status': 'success',
            'data': commitments_data,
            'count': len(commitments_data)
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@commitment_dashboard_bp.route('/send-notifications', methods=['POST'])
@login_required
def send_notifications():
    """Send notifications for commitments"""
    try:
        if current_user.role != 'admin':
            return jsonify({
                'status': 'error',
                'message': 'Admin access required'
            }), 403
        
        notification_service = NotificationService()
        commitment_tracker = CommitmentTracker()
        
        # Send batch notifications
        notifications_sent = commitment_tracker.send_commitment_notifications()
        
        # Send daily digest
        digest_sent = notification_service.send_daily_commitment_digest()
        
        return jsonify({
            'status': 'success',
            'message': f'Notifications sent: {notifications_sent}, Daily digest: {"sent" if digest_sent else "failed"}'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@commitment_dashboard_bp.route('/bulk-update', methods=['POST'])
@login_required
def bulk_update():
    """Bulk update commitment status"""
    try:
        data = request.get_json()
        commitment_ids = data.get('commitment_ids', [])
        new_status = data.get('status')
        
        if not commitment_ids or not new_status:
            return jsonify({
                'status': 'error',
                'message': 'Missing commitment_ids or status'
            }), 400
        
        # Convert string to enum
        try:
            status_enum = CommitmentStatus(new_status)
        except ValueError:
            return jsonify({
                'status': 'error',
                'message': f'Invalid status: {new_status}'
            }), 400
        
        commitment_tracker = CommitmentTracker()
        result = commitment_tracker.bulk_update_commitments(
            commitment_ids, status_enum, updated_by=current_user.username
        )
        
        return jsonify({
            'status': 'success',
            'data': result
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@commitment_dashboard_bp.route('/report')
@login_required
def commitment_report():
    """Generate commitment report"""
    try:
        state_name = request.args.get('state')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Parse dates
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        commitment_tracker = CommitmentTracker()
        report = commitment_tracker.generate_commitment_report(
            state_name=state_name,
            start_date=start_date,
            end_date=end_date
        )
        
        return jsonify({
            'status': 'success',
            'data': report
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def get_recent_commitment_activity(limit=10):
    """Get recent commitment activity"""
    activities = []
    
    # Get recent commitment status changes
    recent_commitments = Commitment.query.order_by(Commitment.updated_at.desc()).limit(limit).all()
    
    for commitment in recent_commitments:
        activity = {
            'id': commitment.id,
            'type': 'commitment_update',
            'description': f"Commitment {commitment.id} status changed to {commitment.status.value}",
            'timestamp': commitment.updated_at.isoformat(),
            'details': {
                'commitment_text': commitment.commitment_text[:100] + '...' if len(commitment.commitment_text) > 100 else commitment.commitment_text,
                'query_id': commitment.audit_query.query_id if commitment.audit_query else None,
                'state': commitment.audit_query.state_name if commitment.audit_query else None
            }
        }
        activities.append(activity)
    
    return activities


def get_commitment_trends():
    """Get commitment trends for the last 30 days"""
    trends = {}
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # Daily commitment counts
    daily_counts = db.session.query(
        func.date(Commitment.created_at).label('date'),
        func.count(Commitment.id).label('count')
    ).filter(
        Commitment.created_at >= start_date
    ).group_by(
        func.date(Commitment.created_at)
    ).order_by('date').all()
    
    trends['daily_created'] = [
        {'date': str(item.date), 'count': item.count} 
        for item in daily_counts
    ]
    
    # Status distribution
    status_counts = db.session.query(
        Commitment.status,
        func.count(Commitment.id).label('count')
    ).group_by(Commitment.status).all()
    
    trends['status_distribution'] = [
        {'status': item.status.value, 'count': item.count} 
        for item in status_counts
    ]
    
    # Completion rate over time
    completed_daily = db.session.query(
        func.date(Commitment.completed_at).label('date'),
        func.count(Commitment.id).label('count')
    ).filter(
        Commitment.completed_at >= start_date,
        Commitment.status == CommitmentStatus.completed
    ).group_by(
        func.date(Commitment.completed_at)
    ).order_by('date').all()
    
    trends['daily_completed'] = [
        {'date': str(item.date), 'count': item.count} 
        for item in completed_daily
    ]
    
    return trends
