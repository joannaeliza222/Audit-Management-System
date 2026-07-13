"""
Audit Analytics Routes
Provides audit analytics with state-wise data and visualizations
"""

from flask import Blueprint, render_template, jsonify, current_app, send_file, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime

from app import db
from app.models import User, FAQ, DraftFAQ, DraftStatus
from app.utils.embeddings import login_required, current_user, fetch_data
from sqlalchemy import func, case
import json

audit_analytics_bp = Blueprint('audit_analytics', __name__)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


@audit_analytics_bp.route('/audit-analytics')
@login_required
def audit_analytics():
    """Audit analytics dashboard with state-wise data and visualizations"""
    try:
        # Get state-wise analytics data
        state_analytics = get_state_analytics()
        
        # Calculate summary statistics from state_analytics (same as API)
        total_questions = sum(s['total'] for s in state_analytics)
        answered_queries = sum(s['answered'] for s in state_analytics)
        pending_queries = sum(s['pending'] for s in state_analytics)
        under_review_queries = sum(s['under_review'] for s in state_analytics)
        
        # Create status distribution object
        status_distribution = {
            'answered': answered_queries,
            'pending': pending_queries,
            'under_review': under_review_queries
        }
        
        # Get total states count
        total_states = len(state_analytics)
        unanswered_questions = pending_queries  # For consistency
        
        # Get trend data (mock for now - can be enhanced with real time series data)
        trend_data = get_trend_data()
        
        # Generate multiple chart types
        trend_chart_data = generate_trend_chart_data(state_analytics)
        bar_chart_data = generate_bar_chart_data(state_analytics)
        
        # Get unique states for filter dropdown
        all_states = sorted([s['state'] for s in state_analytics])
        
        return render_template('audit_analytics.html',
                             user=current_user(),
                             role=current_user().role,
                             state_analytics=state_analytics,
                             all_states=all_states,
                             total_states=total_states,
                             total_questions=total_questions,
                             unanswered_questions=unanswered_questions,
                             status_distribution=status_distribution,
                             trend_data=trend_data,
                             trend_chart_data=trend_chart_data,
                             bar_chart_data=bar_chart_data)
    
    except Exception as e:
        current_app.logger.error(f"Error loading audit analytics: {e}")
        return render_template('audit_analytics.html',
                             user=current_user(),
                             role=current_user().role,
                             state_analytics=[],
                             all_states=[],
                             total_states=0,
                             total_questions=0,
                             unanswered_questions=0,
                             status_distribution={},
                             trend_data=[],
                             trend_chart_data=None,
                             bar_chart_data=None)


@audit_analytics_bp.route('/api/audit-analytics-data')
@login_required
def audit_analytics_api():
    """API endpoint for audit analytics data"""
    try:
        state_analytics = get_state_analytics()
        status_distribution = get_status_distribution()
        trend_data = get_trend_data()
        
        return jsonify({
            'success': True,
            'data': {
                'state_analytics': state_analytics,
                'status_distribution': status_distribution,
                'trend_data': trend_data
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Error in audit analytics API: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@audit_analytics_bp.route('/api/filtered-charts')
@login_required
def filtered_charts():
    """Generate filtered charts based on selected filters"""
    try:
        # Get filter parameters
        selected_state = request.args.get('state', '')
        period = int(request.args.get('period', 30))
        
        # Get state analytics data
        state_analytics = get_state_analytics()
        
        if not state_analytics:
            return jsonify({'success': False, 'error': 'No data available'})
        
        # Filter data if state is selected
        if selected_state:
            filtered_data = [s for s in state_analytics if s['state'] == selected_state]
            if not filtered_data:
                return jsonify({'success': False, 'error': 'No data for selected state'})
            state_analytics = filtered_data
        
        # Generate charts
        trend_chart_data = generate_trend_chart_data(state_analytics, days=period)
        bar_chart_data = generate_bar_chart_data(state_analytics)
        
        # Calculate summary statistics
        total_queries = sum(s['total'] for s in state_analytics)
        answered_queries = sum(s['answered'] for s in state_analytics)
        pending_queries = sum(s['pending'] for s in state_analytics)
        under_review_queries = sum(s['under_review'] for s in state_analytics)
        
        return jsonify({
            'success': True,
            'trend_chart_data': trend_chart_data,
            'bar_chart_data': bar_chart_data,
            'summary': {
                'total_queries': total_queries,
                'answered': answered_queries,
                'pending': pending_queries,
                'under_review': under_review_queries
            },
            'state_analytics': state_analytics,
            'filters_applied': {
                'state': selected_state,
                'period': period
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Error generating filtered charts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def generate_trend_chart_data(state_analytics, days=30):
    """Generate trend chart data for Chart.js"""
    try:
        if not state_analytics:
            return None
        
        # Get real daily trend data from database
        from datetime import datetime, timedelta
        
        dates = []
        incoming_queries = []
        answered_queries = []
        
        # Generate data for the last N days
        base_date = datetime.now() - timedelta(days=days)
        
        for i in range(days):
            current_date = base_date + timedelta(days=i)
            dates.append(current_date.strftime('%Y-%m-%d'))
            
            # Get real daily counts from FAQ table (answered queries)
            daily_answered = db.session.query(func.count(FAQ.id)).filter(
                func.date(FAQ.timestamp) == current_date.date(),
                FAQ.reply.isnot(None),
                FAQ.reply != ''
            ).scalar() or 0
            
            # Get real daily counts from DraftFAQ table (incoming/pending queries)
            daily_incoming = db.session.query(func.count(DraftFAQ.id)).filter(
                func.date(DraftFAQ.created_at) == current_date.date()
            ).scalar() or 0
            
            incoming_queries.append(daily_incoming)
            answered_queries.append(daily_answered)
        
        # Create Chart.js compatible data
        chart_data = {
            'data': {
                'labels': dates,
                'datasets': [
                    {
                        'label': 'Daily Incoming Queries',
                        'data': incoming_queries,
                        'borderColor': '#0077be',
                        'backgroundColor': 'rgba(0, 119, 190, 0.3)',
                        'fill': True,
                        'tension': 0.4
                    },
                    {
                        'label': 'Daily Answered Queries',
                        'data': answered_queries,
                        'borderColor': '#28a745',
                        'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                        'fill': False,
                        'tension': 0.4
                    }
                ]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': 'Daily Incoming Queries Trend (Last 30 Days)',
                        'font': {'size': 16, 'family': 'Poppins'}
                    },
                    'legend': {
                        'position': 'top'
                    }
                },
                'scales': {
                    'x': {
                        'title': {
                            'display': True,
                            'text': 'Date'
                        },
                        'ticks': {
                            'maxRotation': 45,
                            'minRotation': 45
                        }
                    },
                    'y': {
                        'title': {
                            'display': True,
                            'text': 'Number of Queries'
                        },
                        'beginAtZero': True
                    }
                }
            }
        }
        
        return chart_data
    
    except Exception as e:
        current_app.logger.error(f"Error generating trend chart data: {e}")
        return None


def generate_bar_chart_data(state_analytics):
    """Generate bar chart data for Chart.js"""
    try:
        if not state_analytics:
            return None
        
        # Get top 8 states by total queries
        top_states = state_analytics[:8]
        states = [s['state'] for s in top_states]
        answered = [s['answered'] for s in top_states]
        pending = [s['pending'] for s in top_states]
        under_review = [s['under_review'] for s in top_states]
        
        # Create Chart.js compatible data
        chart_data = {
            'data': {
                'labels': states,
                'datasets': [
                    {
                        'label': 'Answered',
                        'data': answered,
                        'backgroundColor': '#45B7D1'
                    },
                    {
                        'label': 'Pending',
                        'data': pending,
                        'backgroundColor': '#FFD93D'
                    },
                    {
                        'label': 'Under Review',
                        'data': under_review,
                        'backgroundColor': '#96CEB4'
                    }
                ]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': 'Query Status by State',
                        'font': {'size': 16, 'family': 'Poppins'}
                    },
                    'legend': {
                        'position': 'top'
                    }
                },
                'scales': {
                    'x': {
                        'title': {
                            'display': True,
                            'text': 'States'
                        },
                        'ticks': {
                            'maxRotation': 45,
                            'minRotation': 45
                        }
                    },
                    'y': {
                        'title': {
                            'display': True,
                            'text': 'Number of Queries'
                        },
                        'beginAtZero': True
                    }
                }
            }
        }
        
        return chart_data
    
    except Exception as e:
        current_app.logger.error(f"Error generating bar chart data: {e}")
        return None


def get_state_analytics():
    """Get state-wise analytics data"""
    try:
        # Get answered queries from FAQ table (records moved from DraftFAQ to FAQ)
        answered_data = db.session.query(
            FAQ.state_name,
            func.count(FAQ.id).label('answered')
        ).filter(
            FAQ.state_name.isnot(None),
            FAQ.state_name != ''
        ).group_by(FAQ.state_name).all()
        
        # Get pending queries from DraftFAQ table (all drafts without replies)
        pending_data = db.session.query(
            DraftFAQ.state_name,
            func.count(DraftFAQ.id).label('pending')
        ).filter(
            DraftFAQ.state_name.isnot(None),
            DraftFAQ.state_name != '',
            DraftFAQ.reply.is_(None) | (DraftFAQ.reply == '')
        ).group_by(DraftFAQ.state_name).all()
        
        # Get under review queries from DraftFAQ table (drafts with replies but not merged)
        under_review_data = db.session.query(
            DraftFAQ.state_name,
            func.count(DraftFAQ.id).label('under_review')
        ).filter(
            DraftFAQ.state_name.isnot(None),
            DraftFAQ.state_name != '',
            DraftFAQ.reply.isnot(None),
            DraftFAQ.reply != '',
            DraftFAQ.status != DraftStatus.merged
        ).group_by(DraftFAQ.state_name).all()
        
        # Create dictionaries for each data type
        answered_dict = {row.state_name: row.answered or 0 for row in answered_data}
        pending_dict = {row.state_name: row.pending for row in pending_data}
        under_review_dict = {row.state_name: row.under_review for row in under_review_data}
        
        # Get all unique states from all data sources
        all_states = set()
        all_states.update(answered_dict.keys())
        all_states.update(pending_dict.keys())
        all_states.update(under_review_dict.keys())
        
        # Combine the data
        state_analytics = []
        for state_name in all_states:
            answered = answered_dict.get(state_name, 0)
            pending = pending_dict.get(state_name, 0)
            under_review = under_review_dict.get(state_name, 0)
            total = answered + pending + under_review
            
            analytics = {
                'state': state_name,
                'total': total,
                'answered': answered,
                'pending': pending,
                'under_review': under_review
            }
            state_analytics.append(analytics)
        
        # Sort by total count descending
        state_analytics.sort(key=lambda x: x['total'], reverse=True)
        
        return state_analytics
    
    except Exception as e:
        current_app.logger.error(f"Error getting state analytics: {e}")
        return []


def get_status_distribution():
    """Get overall status distribution"""
    try:
        # Get answered count
        answered_count = FAQ.query.filter(
            FAQ.reply.isnot(None),
            FAQ.reply != '',
            FAQ.state_name.isnot(None),
            FAQ.state_name != ''
        ).count()
        
        # Get pending count
        pending_count = FAQ.query.filter(
            (FAQ.reply.is_(None) | (FAQ.reply == '')),
            FAQ.state_name.isnot(None),
            FAQ.state_name != ''
        ).count()
        
        # Get under review count (drafts)
        under_review_count = DraftFAQ.query.filter(
            DraftFAQ.reply.is_(None) | (DraftFAQ.reply == ''),
            DraftFAQ.state_name.isnot(None),
            DraftFAQ.state_name != ''
        ).count()
        
        return {
            'answered': answered_count,
            'pending': pending_count,
            'under_review': under_review_count
        }
    
    except Exception as e:
        current_app.logger.error(f"Error getting status distribution: {e}")
        return {'answered': 0, 'pending': 0, 'under_review': 0}


def get_trend_data():
    """Get trend data for analytics (mock data for now)"""
    try:
        # This can be enhanced with real time series data
        # For now, return mock trend data
        import random
        
        trend_data = []
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
        
        for month in months:
            trend_data.append({
                'month': month,
                'answered': random.randint(50, 150),
                'pending': random.randint(20, 80),
                'under_review': random.randint(10, 40)
            })
        
        return trend_data
    
    except Exception as e:
        current_app.logger.error(f"Error getting trend data: {e}")
        return []
