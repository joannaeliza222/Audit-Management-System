from datetime import datetime, timedelta
from typing import List, Dict, Optional
from flask import current_app
from sqlalchemy import and_, or_

from app import db
from app.audit_models import AuditQuery, Commitment, CommitmentStatus, QueryVersion, AuditQueryStatus


class CommitmentTracker:
    """Service for tracking and managing commitments made in audit query responses"""
    
    def __init__(self):
        self.notification_threshold_days = 7  # Notify 7 days before due date
        self.overdue_threshold_days = 0     # Mark as overdue on due date
    
    def create_commitment_from_response(self, audit_query_id: int, response_text: str, 
                                      detected_by: str = "system") -> List[Commitment]:
        """Extract and create commitments from response text"""
        from app.services.query_intelligence import QueryIntelligenceService
        
        intelligence_service = QueryIntelligenceService()
        detected_commitments = intelligence_service.detect_commitments(response_text)
        
        created_commitments = []
        
        for commitment_data in detected_commitments:
            commitment = Commitment(
                audit_query_id=audit_query_id,
                commitment_text=commitment_data['text'],
                commitment_type=commitment_data['type'],
                target_date=datetime.strptime(commitment_data['target_date'], '%Y-%m-%d').date() 
                               if commitment_data['target_date'] else None,
                status=CommitmentStatus.pending,
                detected_at=datetime.utcnow()
            )
            
            db.session.add(commitment)
            created_commitments.append(commitment)
        
        if created_commitments:
            db.session.commit()
            current_app.logger.info(f"Created {len(created_commitments)} commitments for query {audit_query_id}")
        
        return created_commitments
    
    def update_commitment_status(self, commitment_id: int, new_status: CommitmentStatus, 
                               notes: str = None, updated_by: str = None) -> bool:
        """Update commitment status with tracking"""
        commitment = Commitment.query.get(commitment_id)
        if not commitment:
            return False
        
        old_status = commitment.status
        commitment.status = new_status
        commitment.updated_at = datetime.utcnow()
        
        # Set completion date if completed
        if new_status == CommitmentStatus.completed:
            commitment.completed_at = datetime.utcnow()
        
        # Create version history for the associated audit query
        audit_query = AuditQuery.query.get(commitment.audit_query_id)
        if audit_query:
            version = QueryVersion(
                audit_query_id=audit_query.id,
                version_number=self.get_next_version_number(audit_query.id),
                change_type='commitment_updated',
                changed_by=updated_by or 'system',
                change_reason=f"Commitment {commitment_id} status changed from {old_status.value} to {new_status.value}"
            )
            db.session.add(version)
        
        db.session.commit()
        
        current_app.logger.info(f"Commitment {commitment_id} status updated: {old_status.value} -> {new_status.value}")
        return True
    
    def get_overdue_commitments(self, state_name: str = None) -> List[Commitment]:
        """Get all overdue commitments"""
        today = datetime.now().date()
        
        query = Commitment.query.filter(
            Commitment.target_date < today,
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        )
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        return query.order_by(Commitment.target_date.asc()).all()
    
    def get_upcoming_commitments(self, days_ahead: int = 7, state_name: str = None) -> List[Commitment]:
        """Get commitments due in the next N days"""
        today = datetime.now().date()
        future_date = today + timedelta(days=days_ahead)
        
        query = Commitment.query.filter(
            Commitment.target_date.between(today, future_date),
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        )
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        return query.order_by(Commitment.target_date.asc()).all()
    
    def get_commitment_dashboard_data(self, state_name: str = None) -> Dict:
        """Get comprehensive commitment data for dashboard"""
        today = datetime.now().date()
        
        # Base query
        query = Commitment.query
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        # Status breakdown
        status_counts = {}
        for status in CommitmentStatus:
            count = query.filter(Commitment.status == status).count()
            status_counts[status.value] = count
        
        # Overdue commitments
        overdue_query = query.filter(
            Commitment.target_date < today,
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        )
        overdue_count = overdue_query.count()
        
        # Upcoming commitments (next 30 days)
        upcoming_date = today + timedelta(days=30)
        upcoming_query = query.filter(
            Commitment.target_date.between(today, upcoming_date),
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        )
        upcoming_count = upcoming_query.count()
        
        # Completion rate (last 90 days)
        ninety_days_ago = today - timedelta(days=90)
        recent_query = query.filter(Commitment.created_at >= ninety_days_ago)
        total_recent = recent_query.count()
        completed_recent = recent_query.filter(Commitment.status == CommitmentStatus.completed).count()
        completion_rate = (completed_recent / total_recent * 100) if total_recent > 0 else 0
        
        # High priority overdue commitments
        high_priority_overdue = overdue_query.join(AuditQuery).filter(
            AuditQuery.priority.in_(['high', 'critical'])
        ).count()
        
        return {
            'state': state_name or 'All States',
            'total_commitments': query.count(),
            'status_breakdown': status_counts,
            'overdue_count': overdue_count,
            'upcoming_count': upcoming_count,
            'completion_rate_90_days': round(completion_rate, 1),
            'high_priority_overdue': high_priority_overdue,
            'critical_issues': self.get_critical_issues(state_name)
        }
    
    def get_critical_issues(self, state_name: str = None) -> List[Dict]:
        """Identify critical commitment issues requiring immediate attention"""
        issues = []
        today = datetime.now().date()
        
        # Base query
        query = Commitment.query.join(AuditQuery)
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        # Critical overdue commitments
        critical_overdue = query.filter(
            Commitment.target_date < today - timedelta(days=14),  # More than 2 weeks overdue
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress]),
            AuditQuery.priority == 'critical'
        ).all()
        
        if critical_overdue:
            issues.append({
                'type': 'critical_overdue',
                'severity': 'critical',
                'count': len(critical_overdue),
                'description': f"{len(critical_overdue)} critical commitments are more than 2 weeks overdue",
                'commitments': [{'id': c.id, 'text': c.commitment_text[:100], 'days_overdue': (today - c.target_date).days} for c in critical_overdue[:5]]
            })
        
        # High volume of overdue commitments
        all_overdue = query.filter(
            Commitment.target_date < today,
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        ).count()
        
        if all_overdue > 20:
            issues.append({
                'type': 'high_overdue_volume',
                'severity': 'high',
                'count': all_overdue,
                'description': f"High volume of overdue commitments: {all_overdue} total"
            })
        
        # Stagnant commitments (no update for 30+ days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        stagnant = query.filter(
            Commitment.updated_at < thirty_days_ago,
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        ).count()
        
        if stagnant > 10:
            issues.append({
                'type': 'stagnant_commitments',
                'severity': 'medium',
                'count': stagnant,
                'description': f"{stagnant} commitments haven't been updated in over 30 days"
            })
        
        return issues
    
    def generate_commitment_report(self, state_name: str = None, start_date: datetime = None, 
                                  end_date: datetime = None) -> Dict:
        """Generate comprehensive commitment report"""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=90)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Base query
        query = Commitment.query.filter(
            Commitment.created_at >= start_date,
            Commitment.created_at <= end_date
        )
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        commitments = query.all()
        
        # Analyze by type
        type_analysis = {}
        for commitment in commitments:
            c_type = commitment.commitment_type or 'other'
            if c_type not in type_analysis:
                type_analysis[c_type] = {'total': 0, 'completed': 0, 'overdue': 0}
            
            type_analysis[c_type]['total'] += 1
            if commitment.status == CommitmentStatus.completed:
                type_analysis[c_type]['completed'] += 1
            elif (commitment.target_date and commitment.target_date < datetime.now().date() and 
                  commitment.status in [CommitmentStatus.pending, CommitmentStatus.in_progress]):
                type_analysis[c_type]['overdue'] += 1
        
        # Calculate completion times
        completed_commitments = [c for c in commitments if c.status == CommitmentStatus.completed and c.completed_at]
        completion_times = []
        
        for commitment in completed_commitments:
            if commitment.detected_at:
                days = (commitment.completed_at - commitment.detected_at).days
                if 0 <= days <= 365:  # Filter reasonable completion times
                    completion_times.append(days)
        
        avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0
        
        # State-wise analysis (if not filtered by state)
        state_analysis = {}
        if not state_name:
            for commitment in commitments:
                state = commitment.audit_query.state_name if commitment.audit_query else 'Unknown'
                if state not in state_analysis:
                    state_analysis[state] = {'total': 0, 'completed': 0, 'overdue': 0}
                
                state_analysis[state]['total'] += 1
                if commitment.status == CommitmentStatus.completed:
                    state_analysis[state]['completed'] += 1
                elif (commitment.target_date and commitment.target_date < datetime.now().date() and 
                      commitment.status in [CommitmentStatus.pending, CommitmentStatus.in_progress]):
                    state_analysis[state]['overdue'] += 1
        
        return {
            'report_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'state_filter': state_name or 'All States'
            },
            'summary': {
                'total_commitments': len(commitments),
                'completed_commitments': len(completed_commitments),
                'overdue_commitments': len([c for c in commitments if 
                                          c.target_date and c.target_date < datetime.now().date() and 
                                          c.status in [CommitmentStatus.pending, CommitmentStatus.in_progress]]),
                'average_completion_time_days': round(avg_completion_time, 1)
            },
            'type_analysis': type_analysis,
            'state_analysis': state_analysis,
            'recommendations': self.generate_commitment_recommendations(commitments)
        }
    
    def generate_commitment_recommendations(self, commitments: List[Commitment]) -> List[str]:
        """Generate actionable recommendations based on commitment data"""
        recommendations = []
        
        if not commitments:
            return recommendations
        
        # Analyze completion rates
        total = len(commitments)
        completed = len([c for c in commitments if c.status == CommitmentStatus.completed])
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        if completion_rate < 50:
            recommendations.append("Consider implementing a commitment tracking system to improve completion rates")
        
        # Analyze overdue commitments
        overdue = len([c for c in commitments if 
                      c.target_date and c.target_date < datetime.now().date() and 
                      c.status in [CommitmentStatus.pending, CommitmentStatus.in_progress]])
        
        if overdue > total * 0.2:  # More than 20% overdue
            recommendations.append("Review commitment timelines and set more realistic target dates")
        
        # Analyze commitment types
        type_counts = {}
        for commitment in commitments:
            c_type = commitment.commitment_type or 'other'
            type_counts[c_type] = type_counts.get(c_type, 0) + 1
        
        if 'implementation' in type_counts and type_counts['implementation'] > total * 0.4:
            recommendations.append("Focus on improving implementation processes and resource allocation")
        
        # Analyze response times
        recent_commitments = [c for c in commitments if c.created_at >= datetime.utcnow() - timedelta(days=30)]
        if len(recent_commitments) > 0:
            avg_detection_delay = sum([(c.created_at - c.audit_query.created_at).days 
                                     for c in recent_commitments if c.audit_query]) / len(recent_commitments)
            
            if avg_detection_delay > 7:
                recommendations.append("Implement automated commitment detection to reduce identification delays")
        
        return recommendations
    
    def get_next_version_number(self, audit_query_id: int) -> int:
        """Get next version number for audit query"""
        max_version = db.session.query(db.func.max(QueryVersion.version_number)).filter(
            QueryVersion.audit_query_id == audit_query_id
        ).scalar()
        
        return (max_version or 0) + 1
    
    def send_commitment_notifications(self) -> int:
        """Send notifications for upcoming and overdue commitments"""
        notifications_sent = 0
        
        # Upcoming commitments
        upcoming = self.get_upcoming_commitments(self.notification_threshold_days)
        for commitment in upcoming:
            if not commitment.overdue_notified:
                # Send notification (implement email/notification logic)
                self.send_notification(commitment, 'upcoming')
                notifications_sent += 1
        
        # Overdue commitments
        overdue = self.get_overdue_commitments()
        for commitment in overdue:
            if not commitment.overdue_notified:
                # Send notification
                self.send_notification(commitment, 'overdue')
                notifications_sent += 1
                commitment.overdue_notified = True
        
        db.session.commit()
        return notifications_sent
    
    def send_notification(self, commitment: Commitment, notification_type: str):
        """Send notification for commitment using the notification service"""
        try:
            from app.services.notification_service import NotificationService
            
            notification_service = NotificationService()
            success = notification_service.send_commitment_notification(
                commitment, notification_type
            )
            
            if success:
                current_app.logger.info(f"Successfully sent {notification_type} notification for commitment {commitment.id}")
            else:
                current_app.logger.warning(f"Failed to send {notification_type} notification for commitment {commitment.id}")
                
        except ImportError:
            # Fallback to basic logging if notification service not available
            current_app.logger.info(f"Notification service not available - {notification_type} notification for commitment {commitment.id}")
            
            # Example notification content (for logging)
            if notification_type == 'overdue':
                message = f"Commitment overdue: {commitment.commitment_text[:100]}..."
            else:
                days_until_due = (commitment.target_date - datetime.now().date()).days
                message = f"Commitment due in {days_until_due} days: {commitment.commitment_text[:100]}..."
            
            current_app.logger.info(f"Notification: {message}")
        except Exception as e:
            current_app.logger.error(f"Error sending notification: {str(e)}")
    
    def bulk_update_commitments(self, commitment_ids: List[int], new_status: CommitmentStatus, 
                               updated_by: str = None) -> Dict:
        """Bulk update multiple commitments"""
        updated_count = 0
        failed_ids = []
        
        for commitment_id in commitment_ids:
            try:
                success = self.update_commitment_status(commitment_id, new_status, updated_by=updated_by)
                if success:
                    updated_count += 1
                else:
                    failed_ids.append(commitment_id)
            except Exception as e:
                current_app.logger.error(f"Failed to update commitment {commitment_id}: {str(e)}")
                failed_ids.append(commitment_id)
        
        return {
            'updated_count': updated_count,
            'failed_count': len(failed_ids),
            'failed_ids': failed_ids
        }
