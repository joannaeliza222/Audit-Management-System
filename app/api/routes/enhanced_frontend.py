"""
Enhanced Frontend Routes
Provides routes for the enhanced AMS frontend components
"""

from flask import Blueprint, render_template, request, jsonify, session, current_app, flash, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app import db
from app.models import User, FAQ, DataDump, DraftFAQ
from app.audit_models import AuditQuery, Commitment, CommitmentStatus
from app.utils.embeddings import login_required, current_user, fetch_data
from app.services.enhanced_query_tracker import EnhancedQueryTracker


enhanced_frontend_bp = Blueprint('enhanced_frontend', __name__)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Initialize services
query_tracker = EnhancedQueryTracker()


@enhanced_frontend_bp.route('/')
@login_required
def enhanced_index():
    """Enhanced dashboard homepage"""
    try:
        role = current_user().role if current_user() else 'viewer'
        
        # Get real-time statistics
        stats = get_dashboard_stats()
        
        return render_template('enhanced_index.html', 
                             user=current_user(), 
                             role=role,
                             stats=stats)
    except Exception as e:
        current_app.logger.error(f"Error loading enhanced index: {e}")
        return render_template('enhanced_index.html', 
                             user=current_user(), 
                             role='viewer',
                             stats={})


def get_dashboard_stats():
    """Get real-time dashboard statistics"""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        # Get last 30 days date
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Count pending queries from DraftFAQ (all drafts without replies)
        pending_queries_count = db.session.query(func.count(DraftFAQ.id)).filter(
            DraftFAQ.reply.is_(None) | (DraftFAQ.reply == '')
        ).scalar() or 0
        
        # Count answered queries from FAQ table (records moved from DraftFAQ to FAQ)
        answered_queries_count = db.session.query(func.count(FAQ.id)).scalar() or 0
        
        # Count total queries (DraftFAQ + FAQ)
        total_queries_count = db.session.query(func.count(DraftFAQ.id)).scalar() or 0 + db.session.query(func.count(FAQ.id)).scalar() or 0
        
        # Count queries under review (DraftFAQ with replies but not merged)
        from app.models import DraftStatus
        under_review_count = db.session.query(func.count(DraftFAQ.id)).filter(
            DraftFAQ.reply.isnot(None),
            DraftFAQ.reply != '',
            DraftFAQ.status != DraftStatus.merged
        ).scalar() or 0
        
        # Count total states
        total_states = int(db.session.query(func.count(func.distinct(DraftFAQ.state_name))).filter(
            DraftFAQ.state_name.isnot(None),
            DraftFAQ.state_name != ''
        ).scalar() or 0)
        
        # Calculate changes (placeholder for now)
        pending_change = 12.5
        answered_change = 8.3
        ai_change = 2.1
        
        # Get commitments data
        total_commitments = db.session.query(func.count(Commitment.id)).scalar() or 0
        overdue_commitments = db.session.query(func.count(Commitment.id)).filter(
            Commitment.status == CommitmentStatus.overdue
        ).scalar() or 0
        
        stats = {
            'pending_queries_count': pending_queries_count,
            'answered_queries_count': answered_queries_count,
            'total_queries_count': total_queries_count,
            'under_review_count': under_review_count,
            'total_states_count': total_states,
            'total_questions': pending_queries_count + answered_queries_count,
            'unanswered_questions': pending_queries_count,
            'pending_change': pending_change,
            'answered_change': answered_change,
            'under_review_change': ai_change,
            'total_commitments': total_commitments,
            'overdue_commitments': overdue_commitments,
            'commitment_completion_rate': round(((total_commitments - overdue_commitments) / total_commitments * 100) if total_commitments > 0 else 0, 1)
        }
        
        return stats
        
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard stats: {e}")
        return {
            'pending_queries_count': 0,
            'answered_queries_count': 0,
            'total_queries_count': 0,
            'under_review_count': 0,
            'total_states_count': 0,
            'total_questions': 0,
            'unanswered_questions': 0,
            'pending_change': 0,
            'answered_change': 0,
            'ai_change': 0,
            'total_commitments': 0,
            'overdue_commitments': 0,
            'commitment_completion_rate': 0
        }


@enhanced_frontend_bp.route('/create-query', methods=['GET', 'POST'])
@login_required
def create_query():
    """Create Query page"""
    if request.method == 'POST':
        try:
            # Get form data
            memo_id = request.form.get('memo_id', '').strip()
            state = request.form.get('state', '').strip()
            subject = request.form.get('subject', '').strip()
            query_details = request.form.get('query_details', '').strip()
            query_date = request.form.get('query_date', '').strip()
            reply = request.form.get('reply', '').strip()
            
            # Validate required fields (only state, date, subject are mandatory)
            if not state or not query_date or not subject:
                flash('State, Date, and Subject are required fields', 'danger')
                return redirect(url_for('enhanced_frontend.create_query'))
            
            # Create new query in DraftFAQ table
            from app.models import DraftFAQ, DraftStatus
            from app.utils.embeddings import normalize_text, get_bert_embeddings
            from datetime import datetime
            
            # Normalize query for uniqueness
            norm_query = normalize_text(subject)
            
            # Create draft query using SQLAlchemy ORM
            new_draft = DraftFAQ(
                subject=subject,
                query_description=query_details,
                norm_query=norm_query,
                reply=reply if reply else None,
                memo_id=memo_id if memo_id else None,
                state_name=state,
                query_date=datetime.strptime(query_date, '%Y-%m-%d') if query_date else datetime.utcnow().date(),
                status=DraftStatus.pending if not reply else DraftStatus.admin_draft,
                created_by=session.get('email'),
                created_at=datetime.utcnow()
            )
            
            # Add embedding if query details provided
            if query_details:
                try:
                    embedding = get_bert_embeddings(query_details)
                    if embedding is not None:
                        new_draft.embedding = embedding
                except Exception as e:
                    current_app.logger.warning(f"Failed to generate embedding: {e}")
            
            db.session.add(new_draft)
            db.session.flush()  # Get the ID without committing
            
            # Detect future issues in query details and reply
            from app.utils.embeddings import detect_future_issue
            from sqlalchemy import text
            
            # Check query details for future issues
            if query_details:
                future_issue = detect_future_issue(query_details)
                if future_issue:
                    # Use raw SQL to create future issue tracker
                    issue_sql = text("""
                        INSERT INTO future_issue_tracker (
                            related_draft_id, description, detected_at, status
                        ) VALUES (
                            :related_draft_id, :description, :detected_at, :status
                        )
                    """)
                    
                    db.session.execute(issue_sql, {
                        'related_draft_id': new_draft.id,
                        'description': future_issue,
                        'detected_at': datetime.utcnow(),
                        'status': 'not addressed'
                    })
            
            # Check reply for future issues
            if reply:
                future_issue = detect_future_issue(reply)
                if future_issue:
                    # Use raw SQL to create future issue tracker
                    issue_sql = text("""
                        INSERT INTO future_issue_tracker (
                            related_draft_id, description, detected_at, status
                        ) VALUES (
                            :related_draft_id, :description, :detected_at, :status
                        )
                    """)
                    
                    db.session.execute(issue_sql, {
                        'related_draft_id': new_draft.id,
                        'description': future_issue,
                        'detected_at': datetime.utcnow(),
                        'status': 'not addressed'
                    })
            
            db.session.commit()
            
            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': True,
                    'message': 'Query created successfully!',
                    'type': 'success'
                })
            else:
                flash('Query created successfully!', 'success')
                return redirect(url_for('enhanced_frontend.enhanced_index'))
            
        except Exception as e:
            current_app.logger.error(f"Error creating query: {e}")
            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Error creating query. Please try again.',
                    'type': 'danger'
                })
            else:
                flash('Error creating query. Please try again.', 'danger')
                return redirect(url_for('enhanced_frontend.create_query'))
    
    # GET request - show the form
    try:
        # Get states for dropdown
        from app.models import DraftFAQ
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
        
        return render_template('create_query.html', 
                             user=current_user(), 
                             role=current_user().role,
                             states=distinct_states)
    except Exception as e:
        current_app.logger.error(f"Error loading create query page: {e}")
        return render_template('create_query.html', 
                             user=current_user(), 
                             role=current_user().role,
                             states=[])


@enhanced_frontend_bp.route('/commitment-dashboard')
@login_required
def commitment_dashboard():
    """Commitment tracking dashboard"""
    try:
        role = current_user().role if current_user() else 'viewer'
        
        # Get commitments data
        commitments = get_commitments_data()
        
        return render_template('commitment_dashboard.html',
                             user=current_user(),
                             role=role,
                             commitments=commitments)
    except Exception as e:
        current_app.logger.error(f"Error loading commitment dashboard: {e}")
        return render_template('commitment_dashboard.html',
                             user=current_user(),
                             role='viewer',
                             commitments=[])


def get_commitments_data():
    """Get commitments data for dashboard"""
    try:
        commitments = Commitment.query.order_by(Commitment.target_date.asc()).all()
        return commitments
    except Exception as e:
        current_app.logger.error(f"Error getting commitments data: {e}")
        return []


@enhanced_frontend_bp.route('/analytics')
@login_required
def analytics():
    """Analytics dashboard"""
    try:
        role = current_user().role if current_user() else 'viewer'
        
        return render_template('analytics.html',
                             user=current_user(),
                             role=role)
    except Exception as e:
        current_app.logger.error(f"Error loading analytics: {e}")
        return render_template('analytics.html',
                             user=current_user(),
                             role='viewer')


@enhanced_frontend_bp.route('/data-dump-analytics')
@login_required
def data_dump_analytics():
    """Data Dump Analytics dashboard"""
    try:
        role = current_user().role if current_user() else 'viewer'
        
        return render_template('data_dump_analytics.html',
                             user=current_user(),
                             role=role)
    except Exception as e:
        current_app.logger.error(f"Error loading data dump analytics: {e}")
        return render_template('data_dump_analytics.html',
                             user=current_user(),
                             role='viewer')


@enhanced_frontend_bp.route('/api/data-dump-analytics')
@login_required
def get_data_dump_analytics():
    """API endpoint for data dump analytics data"""
    try:
        current_app.logger.info("Data dump analytics API called")
        user = current_user()
        current_app.logger.info(f"Current user: {user.email if user else 'None'}")
        from datetime import datetime, timedelta
        from sqlalchemy import func, extract
        
        # Get all data dump requests
        total_requests = DataDump.query.count()
        current_app.logger.info(f"Total requests found: {total_requests}")
        
        # Get requests by status
        status_counts = db.session.query(
            DataDump.status,
            func.count(DataDump.id).label('count')
        ).group_by(DataDump.status).all()
        
        status_distribution = {status: count for status, count in status_counts}
        current_app.logger.info(f"Status distribution: {status_distribution}")
        
        # Get requests by state
        state_counts = db.session.query(
            DataDump.state,
            func.count(DataDump.id).label('count')
        ).filter(DataDump.state.isnot(None)).group_by(DataDump.state).all()
        
        requests_by_state = {state: count for state, count in state_counts}
        current_app.logger.info(f"Requests by state: {requests_by_state}")
        
        # Get daily trends for the last 30 days using request_date (exclude null dates)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        daily_trends = db.session.query(
            extract('year', DataDump.request_date).label('year'),
            extract('month', DataDump.request_date).label('month'),
            extract('day', DataDump.request_date).label('day'),
            func.count(DataDump.id).label('count')
        ).filter(
            DataDump.request_date.isnot(None),
            DataDump.request_date >= thirty_days_ago
        ).group_by(
            extract('year', DataDump.request_date),
            extract('month', DataDump.request_date),
            extract('day', DataDump.request_date)
        ).order_by('year', 'month', 'day').all()
        
        # Format daily trends
        daily_data = {}
        for year, month, day, count in daily_trends:
            if year is not None and month is not None and day is not None:
                day_key = f"{int(year)}-{int(month):02d}-{int(day):02d}"
                daily_data[day_key] = int(count) if count is not None else 0
        
        # Calculate processing times - use shared requests as completed
        completed_requests = DataDump.query.filter(
            DataDump.share_date.isnot(None),
            DataDump.request_date.isnot(None)
        ).all()
        
        processing_times = []
        for req in completed_requests:
            if req.share_date and req.request_date:
                days = (req.share_date - req.request_date).days
                processing_times.append(days)
        
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        # Calculate processing time analysis by state
        processing_time_by_state = {}
        for req in completed_requests:
            if req.share_date and req.request_date and req.state:
                days = (req.share_date - req.request_date).days
                if req.state not in processing_time_by_state:
                    processing_time_by_state[req.state] = []
                processing_time_by_state[req.state].append(days)
        
        # Calculate average processing time by state
        processing_time_analysis = {}
        for state, times in processing_time_by_state.items():
            if times:
                processing_time_analysis[state] = round(sum(times) / len(times), 1)
        
        # Get recent requests
        recent_requests = DataDump.query.order_by(DataDump.request_date.desc()).limit(10).all()
        
        recent_data = []
        for req in recent_requests:
            processing_time = None
            if req.share_date and req.request_date:
                processing_time = f"{(req.share_date - req.request_date).days} days"
            
            # Determine status based on share_date and status field
            display_status = 'completed' if req.share_date else (req.status or 'requested')
            
            recent_data.append({
                'id': req.id,
                'state': req.state or '-',
                'nodal_department': req.nodal_dept or '-',
                'coordinator': req.coordinator_name or req.coordinator or '-',
                'status': display_status,
                'request_date': req.request_date.strftime('%Y-%m-%d') if req.request_date else '-',
                'completed_date': req.share_date.strftime('%Y-%m-%d') if req.share_date else '-',
                'processing_time': processing_time
            })
        
        # Calculate pending and completed requests based on actual data
        pending_requests = DataDump.query.filter(DataDump.share_date.is_(None)).count()
        completed_requests = DataDump.query.filter(DataDump.share_date.isnot(None)).count()
        
        analytics_data = {
            'success': True,
            'analytics': {
                'total_requests': total_requests,
                'pending_requests': pending_requests,
                'completed_requests': completed_requests,
                'avg_processing_time': round(avg_processing_time, 1),
                'status_distribution': status_distribution,
                'requests_by_state': requests_by_state,
                'daily_trends': daily_data,
                'processing_time_analysis': processing_time_analysis,
                'recent_requests': recent_data
            }
        }
        
        current_app.logger.info(f"Final analytics data prepared: {analytics_data}")
        return jsonify(analytics_data)
        
    except Exception as e:
        current_app.logger.error(f"Error getting data dump analytics: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
