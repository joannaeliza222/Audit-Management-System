from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from flask import current_app
from sqlalchemy import func, and_, or_, extract
from collections import defaultdict

from app import db
from app.models import FAQ, DraftFAQ, User
from app.audit_models import AuditQuery, Commitment, CommitmentStatus, AuditQueryStatus, DocumentProcessing


class AnalyticsService:
    """Comprehensive analytics service for audit query management"""
    
    def __init__(self):
        self.default_date_range = 30  # days
    
    def get_dashboard_overview(self, state_name: str = None, days: int = None) -> Dict:
        """Get comprehensive dashboard overview"""
        if days is None:
            days = self.default_date_range
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get various metrics
        query_metrics = self.get_query_metrics(state_name, start_date, end_date)
        commitment_metrics = self.get_commitment_metrics(state_name, start_date, end_date)
        response_metrics = self.get_response_metrics(state_name, start_date, end_date)
        document_metrics = self.get_document_metrics(state_name, start_date, end_date)
        user_metrics = self.get_user_metrics(state_name, start_date, end_date)
        
        # Generate insights
        insights = self.generate_dashboard_insights(query_metrics, commitment_metrics, response_metrics)
        
        return {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            },
            'state_filter': state_name or 'All States',
            'query_metrics': query_metrics,
            'commitment_metrics': commitment_metrics,
            'response_metrics': response_metrics,
            'document_metrics': document_metrics,
            'user_metrics': user_metrics,
            'insights': insights,
            'trends': self.get_trend_data(state_name, days)
        }
    
    def get_query_metrics(self, state_name: str, start_date: datetime, end_date: datetime) -> Dict:
        """Get query-related metrics"""
        # Base query
        query = AuditQuery.query.filter(
            AuditQuery.created_at >= start_date,
            AuditQuery.created_at <= end_date
        )
        
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        # Total queries
        total_queries = query.count()
        
        # Status breakdown
        status_breakdown = {}
        for status in AuditQueryStatus:
            count = query.filter(AuditQuery.status == status).count()
            status_breakdown[status.value] = {
                'count': count,
                'percentage': (count / total_queries * 100) if total_queries > 0 else 0
            }
        
        # Priority breakdown
        priority_breakdown = {}
        priorities = ['low', 'medium', 'high', 'critical']
        for priority in priorities:
            count = query.filter(AuditQuery.priority == priority).count()
            priority_breakdown[priority] = {
                'count': count,
                'percentage': (count / total_queries * 100) if total_queries > 0 else 0
            }
        
        # Department breakdown
        dept_query = query.with_entities(
            AuditQuery.department,
            func.count(AuditQuery.id).label('count')
        ).group_by(AuditQuery.department).order_by(func.count(AuditQuery.id).desc()).limit(10)
        
        department_breakdown = [{'department': dept, 'count': count} for dept, count in dept_query.all()]
        
        # Daily trend
        daily_trend = self.get_daily_query_trend(state_name, start_date, end_date)
        
        return {
            'total_queries': total_queries,
            'status_breakdown': status_breakdown,
            'priority_breakdown': priority_breakdown,
            'department_breakdown': department_breakdown,
            'daily_trend': daily_trend
        }
    
    def get_commitment_metrics(self, state_name: str, start_date: datetime, end_date: datetime) -> Dict:
        """Get commitment-related metrics"""
        # Base query
        query = Commitment.query.filter(
            Commitment.created_at >= start_date,
            Commitment.created_at <= end_date
        )
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        # Total commitments
        total_commitments = query.count()
        
        # Status breakdown
        status_breakdown = {}
        for status in CommitmentStatus:
            count = query.filter(Commitment.status == status).count()
            status_breakdown[status.value] = {
                'count': count,
                'percentage': (count / total_commitments * 100) if total_commitments > 0 else 0
            }
        
        # Overdue commitments
        today = datetime.now().date()
        overdue_count = query.filter(
            Commitment.target_date < today,
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        ).count()
        
        # Upcoming commitments (next 30 days)
        upcoming_date = today + timedelta(days=30)
        upcoming_count = query.filter(
            Commitment.target_date.between(today, upcoming_date),
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        ).count()
        
        # Completion rate
        completed_count = query.filter(Commitment.status == CommitmentStatus.completed).count()
        completion_rate = (completed_count / total_commitments * 100) if total_commitments > 0 else 0
        
        # Average completion time
        completed_commitments = query.filter(Commitment.status == CommitmentStatus.completed).all()
        completion_times = []
        
        for commitment in completed_commitments:
            if commitment.completed_at and commitment.detected_at:
                days = (commitment.completed_at - commitment.detected_at).days
                if 0 <= days <= 365:
                    completion_times.append(days)
        
        avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0
        
        # Commitment types
        type_breakdown = query.with_entities(
            Commitment.commitment_type,
            func.count(Commitment.id).label('count')
        ).group_by(Commitment.commitment_type).order_by(func.count(Commitment.id).desc()).all()
        
        return {
            'total_commitments': total_commitments,
            'status_breakdown': status_breakdown,
            'overdue_count': overdue_count,
            'upcoming_count': upcoming_count,
            'completion_rate': round(completion_rate, 1),
            'average_completion_time_days': round(avg_completion_time, 1),
            'type_breakdown': [{'type': ctype or 'other', 'count': count} for ctype, count in type_breakdown]
        }
    
    def get_response_metrics(self, state_name: str, start_date: datetime, end_date: datetime) -> Dict:
        """Get response-related metrics"""
        # Queries with responses
        responded_query = AuditQuery.query.filter(
            AuditQuery.response_provided.isnot(None),
            AuditQuery.response_date >= start_date,
            AuditQuery.response_date <= end_date
        )
        
        if state_name:
            responded_query = responded_query.filter(AuditQuery.state_name == state_name)
        
        total_responded = responded_query.count()
        
        # Calculate response times
        response_times = []
        for query in responded_query.all():
            if query.date_received and query.response_date:
                days = (query.response_date - query.date_received).days
                if 0 <= days <= 365:
                    response_times.append(days)
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        median_response_time = sorted(response_times)[len(response_times) // 2] if response_times else 0
        
        # Response time distribution
        response_time_distribution = {
            'same_day': len([t for t in response_times if t == 0]),
            '1-3_days': len([t for t in response_times if 1 <= t <= 3]),
            '4-7_days': len([t for t in response_times if 4 <= t <= 7]),
            '8-14_days': len([t for t in response_times if 14 <= t <= 14]),
            '15+_days': len([t for t in response_times if t >= 15])
        }
        
        # Response methods
        method_breakdown = responded_query.with_entities(
            AuditQuery.response_method,
            func.count(AuditQuery.id).label('count')
        ).group_by(AuditQuery.response_method).order_by(func.count(AuditQuery.id).desc()).all()
        
        return {
            'total_responded': total_responded,
            'average_response_time_days': round(avg_response_time, 1),
            'median_response_time_days': median_response_time,
            'response_time_distribution': response_time_distribution,
            'method_breakdown': [{'method': method or 'unknown', 'count': count} for method, count in method_breakdown]
        }
    
    def get_document_metrics(self, state_name: str, start_date: datetime, end_date: datetime) -> Dict:
        """Get document processing metrics"""
        query = DocumentProcessing.query.filter(
            DocumentProcessing.upload_timestamp >= start_date,
            DocumentProcessing.upload_timestamp <= end_date
        )
        
        if state_name:
            # Filter by queries from this state
            query = query.join(AuditQuery, DocumentProcessing.extracted_items).filter(
                AuditQuery.state_name == state_name
            )
        
        total_documents = query.count()
        
        # Processing status breakdown
        status_breakdown = {}
        statuses = ['pending', 'processing', 'completed', 'failed']
        for status in statuses:
            count = query.filter(DocumentProcessing.processing_status == status).count()
            status_breakdown[status] = {
                'count': count,
                'percentage': (count / total_documents * 100) if total_documents > 0 else 0
            }
        
        # File type breakdown
        type_breakdown = query.with_entities(
            DocumentProcessing.file_type,
            func.count(DocumentProcessing.id).label('count')
        ).group_by(DocumentProcessing.file_type).order_by(func.count(DocumentProcessing.id).desc()).all()
        
        # Extraction metrics
        completed_docs = query.filter(DocumentProcessing.processing_status == 'completed').all()
        total_extracted_queries = sum(doc.extracted_queries or 0 for doc in completed_docs)
        total_extracted_qa_pairs = sum(doc.extracted_qa_pairs or 0 for doc in completed_docs)
        
        avg_extraction_confidence = 0
        if completed_docs:
            confidences = [doc.extraction_confidence for doc in completed_docs if doc.extraction_confidence]
            avg_extraction_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            'total_documents': total_documents,
            'status_breakdown': status_breakdown,
            'type_breakdown': [{'type': file_type, 'count': count} for file_type, count in type_breakdown],
            'total_extracted_queries': total_extracted_queries,
            'total_extracted_qa_pairs': total_extracted_qa_pairs,
            'average_extraction_confidence': round(avg_extraction_confidence, 2)
        }
    
    def get_user_metrics(self, state_name: str, start_date: datetime, end_date: datetime) -> Dict:
        """Get user activity metrics"""
        # Active users (users who performed any action)
        active_users = db.session.query(User).filter(
            or_(
                User.id.in_(
                    db.session.query(AuditQuery.assigned_official_email).filter(
                        AuditQuery.created_at >= start_date,
                        AuditQuery.created_at <= end_date
                    )
                ),
                User.id.in_(
                    db.session.query(DocumentProcessing.uploaded_by).filter(
                        DocumentProcessing.upload_timestamp >= start_date,
                        DocumentProcessing.upload_timestamp <= end_date
                    )
                )
            )
        ).count()
        
        # Top contributors
        top_contributors = db.session.query(
            User.name,
            func.count(AuditQuery.id).label('query_count')
        ).join(
            AuditQuery, User.email == AuditQuery.assigned_official_email
        ).filter(
            AuditQuery.created_at >= start_date,
            AuditQuery.created_at <= end_date
        ).group_by(User.id, User.name).order_by(
            func.count(AuditQuery.id).desc()
        ).limit(10).all()
        
        return {
            'active_users': active_users,
            'top_contributors': [{'name': name, 'query_count': count} for name, count in top_contributors]
        }
    
    def get_daily_query_trend(self, state_name: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get daily query creation trend"""
        query = db.session.query(
            func.date(AuditQuery.created_at).label('date'),
            func.count(AuditQuery.id).label('count')
        ).filter(
            AuditQuery.created_at >= start_date,
            AuditQuery.created_at <= end_date
        )
        
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        query = query.group_by(func.date(AuditQuery.created_at)).order_by(func.date(AuditQuery.created_at))
        
        return [{'date': date.isoformat(), 'count': count} for date, count in query.all()]
    
    def get_trend_data(self, state_name: str, days: int) -> Dict:
        """Get trend data for key metrics"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Query volume trend
        query_trend = self.get_daily_query_trend(state_name, start_date, end_date)
        
        # Response time trend (weekly)
        response_time_trend = self.get_weekly_response_time_trend(state_name, start_date, end_date)
        
        # Commitment completion trend
        commitment_trend = self.get_weekly_commitment_trend(state_name, start_date, end_date)
        
        return {
            'query_volume': query_trend,
            'response_times': response_time_trend,
            'commitment_completion': commitment_trend
        }
    
    def get_weekly_response_time_trend(self, state_name: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get weekly average response time trend"""
        query = db.session.query(
            func.date_trunc('week', AuditQuery.response_date).label('week'),
            func.avg(func.datediff(AuditQuery.response_date, AuditQuery.date_received)).label('avg_days')
        ).filter(
            AuditQuery.response_date >= start_date,
            AuditQuery.response_date <= end_date,
            AuditQuery.response_provided.isnot(None)
        )
        
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        query = query.group_by(func.date_trunc('week', AuditQuery.response_date)).order_by(
            func.date_trunc('week', AuditQuery.response_date)
        )
        
        return [{'week': week.isoformat() if week else None, 'avg_days': round(float(avg_days), 1) if avg_days else 0} 
                for week, avg_days in query.all()]
    
    def get_weekly_commitment_trend(self, state_name: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Get weekly commitment completion trend"""
        query = db.session.query(
            func.date_trunc('week', Commitment.completed_at).label('week'),
            func.count(Commitment.id).label('completed_count')
        ).filter(
            Commitment.completed_at >= start_date,
            Commitment.completed_at <= end_date,
            Commitment.status == CommitmentStatus.completed
        )
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        query = query.group_by(func.date_trunc('week', Commitment.completed_at)).order_by(
            func.date_trunc('week', Commitment.completed_at)
        )
        
        return [{'week': week.isoformat() if week else None, 'completed_count': count} 
                for week, count in query.all()]
    
    def generate_dashboard_insights(self, query_metrics: Dict, commitment_metrics: Dict, response_metrics: Dict) -> List[Dict]:
        """Generate actionable insights from metrics"""
        insights = []
        
        # High query volume
        if query_metrics['total_queries'] > 100:
            insights.append({
                'type': 'volume_alert',
                'severity': 'medium',
                'title': 'High Query Volume',
                'description': f"Received {query_metrics['total_queries']} queries in this period",
                'recommendation': 'Consider allocating additional resources for query processing'
            })
        
        # Low response rate
        total_queries = query_metrics['total_queries']
        responded_queries = response_metrics['total_responded']
        if total_queries > 0 and (responded_queries / total_queries) < 0.5:
            insights.append({
                'type': 'response_rate',
                'severity': 'high',
                'title': 'Low Response Rate',
                'description': f"Only {responded_queries}/{total_queries} queries have been responded to",
                'recommendation': 'Review response processes and assign additional staff'
            })
        
        # Slow response times
        if response_metrics['average_response_time_days'] > 7:
            insights.append({
                'type': 'response_time',
                'severity': 'medium',
                'title': 'Slow Response Times',
                'description': f"Average response time is {response_metrics['average_response_time_days']:.1f} days",
                'recommendation': 'Implement response time targets and monitoring'
            })
        
        # High overdue commitments
        if commitment_metrics['overdue_count'] > 10:
            insights.append({
                'type': 'overdue_commitments',
                'severity': 'high',
                'title': 'High Overdue Commitments',
                'description': f"{commitment_metrics['overdue_count']} commitments are overdue",
                'recommendation': 'Review commitment tracking and follow-up processes'
            })
        
        # Low completion rate
        if commitment_metrics['completion_rate'] < 50:
            insights.append({
                'type': 'completion_rate',
                'severity': 'medium',
                'title': 'Low Commitment Completion Rate',
                'description': f"Only {commitment_metrics['completion_rate']:.1f}% of commitments are completed",
                'recommendation': 'Review commitment feasibility and resource allocation'
            })
        
        return insights
    
    def get_state_comparison(self, days: int = 30) -> Dict:
        """Compare metrics across all states"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get all states with queries
        states = db.session.query(AuditQuery.state_name).distinct().all()
        states = [state[0] for state in states if state[0]]
        
        state_metrics = {}
        
        for state in states:
            query_metrics = self.get_query_metrics(state, start_date, end_date)
            commitment_metrics = self.get_commitment_metrics(state, start_date, end_date)
            response_metrics = self.get_response_metrics(state, start_date, end_date)
            
            state_metrics[state] = {
                'total_queries': query_metrics['total_queries'],
                'response_rate': (response_metrics['total_responded'] / query_metrics['total_queries'] * 100) if query_metrics['total_queries'] > 0 else 0,
                'avg_response_time': response_metrics['average_response_time_days'],
                'commitment_completion_rate': commitment_metrics['completion_rate'],
                'overdue_commitments': commitment_metrics['overdue_count']
            }
        
        # Rank states by different metrics
        rankings = {
            'highest_volume': sorted(state_metrics.items(), key=lambda x: x[1]['total_queries'], reverse=True)[:5],
            'fastest_response': sorted(state_metrics.items(), key=lambda x: x[1]['avg_response_time'])[:5],
            'best_completion_rate': sorted(state_metrics.items(), key=lambda x: x[1]['commitment_completion_rate'], reverse=True)[:5]
        }
        
        return {
            'period': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(), 'days': days},
            'state_metrics': state_metrics,
            'rankings': rankings
        }
    
    def export_analytics_data(self, state_name: str = None, days: int = 30, format: str = 'json') -> str:
        """Export analytics data in specified format"""
        dashboard_data = self.get_dashboard_overview(state_name, days)
        
        if format.lower() == 'json':
            import json
            return json.dumps(dashboard_data, indent=2, default=str)
        else:
            # Could implement CSV, Excel export here
            import json
            return json.dumps(dashboard_data, indent=2, default=str)
    
    def get_performance_indicators(self, state_name: str = None) -> Dict:
        """Get key performance indicators (KPIs)"""
        # Use last 90 days for KPI calculation
        days = 90
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        query_metrics = self.get_query_metrics(state_name, start_date, end_date)
        commitment_metrics = self.get_commitment_metrics(state_name, start_date, end_date)
        response_metrics = self.get_response_metrics(state_name, start_date, end_date)
        
        # Calculate KPIs
        kpis = {
            'query_processing_efficiency': self.calculate_query_efficiency(query_metrics, response_metrics),
            'commitment_reliability': commitment_metrics['completion_rate'],
            'response_timeliness': self.calculate_response_timeliness(response_metrics),
            'overall_performance': 0  # Will be calculated below
        }
        
        # Overall performance (weighted average)
        weights = {
            'query_processing_efficiency': 0.3,
            'commitment_reliability': 0.4,
            'response_timeliness': 0.3
        }
        
        kpis['overall_performance'] = sum(
            kpis[key] * weights[key] for key in weights.keys()
        )
        
        # Performance rating
        if kpis['overall_performance'] >= 90:
            rating = 'Excellent'
        elif kpis['overall_performance'] >= 75:
            rating = 'Good'
        elif kpis['overall_performance'] >= 60:
            rating = 'Fair'
        else:
            rating = 'Poor'
        
        kpis['rating'] = rating
        
        return kpis
    
    def calculate_query_efficiency(self, query_metrics: Dict, response_metrics: Dict) -> float:
        """Calculate query processing efficiency score"""
        total_queries = query_metrics['total_queries']
        if total_queries == 0:
            return 0
        
        response_rate = response_metrics['total_responded'] / total_queries
        
        # Factor in response time (faster is better)
        avg_response_time = response_metrics['average_response_time_days']
        time_score = max(0, 100 - (avg_response_time * 10))  # Deduct 10 points per day
        
        # Combine response rate and time score
        efficiency = (response_rate * 50) + (time_score * 0.5)
        return min(100, efficiency)
    
    def calculate_response_timeliness(self, response_metrics: Dict) -> float:
        """Calculate response timeliness score"""
        avg_time = response_metrics['average_response_time_days']
        
        # Score based on average response time
        if avg_time <= 1:
            return 100
        elif avg_time <= 3:
            return 80
        elif avg_time <= 7:
            return 60
        elif avg_time <= 14:
            return 40
        else:
            return 20
