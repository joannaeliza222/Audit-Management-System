from datetime import datetime, timedelta
from typing import List, Dict, Optional
from flask import current_app, render_template
from flask_mail import Message
from sqlalchemy import and_, or_

from app import db, mail
from app.audit_models import AuditQuery, Commitment, CommitmentStatus
from app.models import User, Notification, DraftFAQ, FutureIssueTracker


class NotificationService:
    """Service for sending email notifications for commitments and audit queries"""
    
    def __init__(self):
        self.reminder_days = current_app.config.get('COMMITMENT_REMINDER_DAYS', 7)
        self.enabled = current_app.config.get('NOTIFICATION_ENABLED', True)
    
    def send_commitment_notification(self, commitment: Commitment, notification_type: str, 
                                   recipient_email: str = None) -> bool:
        """Send notification for a specific commitment"""
        if not self.enabled:
            current_app.logger.info("Notifications disabled - skipping commitment notification")
            return False
        
        try:
            # Determine recipient
            if not recipient_email:
                recipient_email = self.get_commitment_recipient(commitment)
            
            if not recipient_email:
                current_app.logger.warning(f"No recipient found for commitment {commitment.id}")
                return False
            
            # Prepare email content
            subject, html_body, text_body = self.prepare_commitment_email(
                commitment, notification_type
            )
            
            # Create and send email
            msg = Message(
                subject=subject,
                recipients=[recipient_email],
                html=html_body,
                body=text_body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            
            mail.send(msg)
            
            current_app.logger.info(f"Sent {notification_type} notification for commitment {commitment.id} to {recipient_email}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to send notification for commitment {commitment.id}: {str(e)}")
            return False
    
    def get_commitment_recipient(self, commitment: Commitment) -> Optional[str]:
        """Get the appropriate recipient email for a commitment"""
        # Try assigned official email first
        if commitment.audit_query and commitment.audit_query.assigned_official_email:
            return commitment.audit_query.assigned_official_email
        
        # Try to find user by name
        if commitment.audit_query and commitment.audit_query.assigned_official:
            user = User.query.filter(
                User.username.ilike(f"%{commitment.audit_query.assigned_official}%")
            ).first()
            if user and user.email:
                return user.email
        
        # Fallback to admin users
        admin_users = User.query.filter_by(role='admin').all()
        if admin_users:
            return admin_users[0].email
        
        return None
    
    def prepare_commitment_email(self, commitment: Commitment, notification_type: str) -> tuple:
        """Prepare email content for commitment notification"""
        query = commitment.audit_query
        
        if notification_type == 'overdue':
            days_overdue = (datetime.now().date() - commitment.target_date).days
            subject = f"OVERDUE: Commitment {commitment.id} - {days_overdue} days late"
            
            html_body = f"""
            <h2 style="color: #d32f2f;">Overdue Commitment Alert</h2>
            <p>A commitment is now overdue and requires immediate attention:</p>
            
            <div style="background-color: #ffebee; padding: 15px; border-left: 4px solid #d32f2f; margin: 15px 0;">
                <h3>Commitment Details:</h3>
                <p><strong>Query ID:</strong> {query.query_id if query else 'N/A'}</p>
                <p><strong>State:</strong> {query.state_name if query else 'N/A'}</p>
                <p><strong>Commitment:</strong> {commitment.commitment_text}</p>
                <p><strong>Due Date:</strong> {commitment.target_date}</p>
                <p><strong>Days Overdue:</strong> <span style="color: #d32f2f; font-weight: bold;">{days_overdue} days</span></p>
                <p><strong>Status:</strong> {commitment.status.value}</p>
            </div>
            
            <p>Please take immediate action to address this overdue commitment.</p>
            <p><a href="{current_app.config.get('SERVER_URL', '')}/review" style="background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Review Commitment</a></p>
            """
            
        elif notification_type == 'upcoming':
            days_until_due = (commitment.target_date - datetime.now().date()).days
            subject = f"Reminder: Commitment {commitment.id} due in {days_until_due} days"
            
            html_body = f"""
            <h2 style="color: #f57c00;">Upcoming Commitment Reminder</h2>
            <p>A commitment is approaching its due date:</p>
            
            <div style="background-color: #fff3e0; padding: 15px; border-left: 4px solid #f57c00; margin: 15px 0;">
                <h3>Commitment Details:</h3>
                <p><strong>Query ID:</strong> {query.query_id if query else 'N/A'}</p>
                <p><strong>State:</strong> {query.state_name if query else 'N/A'}</p>
                <p><strong>Commitment:</strong> {commitment.commitment_text}</p>
                <p><strong>Due Date:</strong> {commitment.target_date}</p>
                <p><strong>Days Until Due:</strong> <span style="color: #f57c00; font-weight: bold;">{days_until_due} days</span></p>
                <p><strong>Status:</strong> {commitment.status.value}</p>
            </div>
            
            <p>Please ensure this commitment is completed before the due date.</p>
            <p><a href="{current_app.config.get('SERVER_URL', '')}/review" style="background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Review Commitment</a></p>
            """
            
        else:  # status_update
            subject = f"Updated: Commitment {commitment.id} status changed to {commitment.status.value}"
            
            html_body = f"""
            <h2 style="color: #388e3c;">Commitment Status Update</h2>
            <p>A commitment status has been updated:</p>
            
            <div style="background-color: #e8f5e8; padding: 15px; border-left: 4px solid #388e3c; margin: 15px 0;">
                <h3>Commitment Details:</h3>
                <p><strong>Query ID:</strong> {query.query_id if query else 'N/A'}</p>
                <p><strong>State:</strong> {query.state_name if query else 'N/A'}</p>
                <p><strong>Commitment:</strong> {commitment.commitment_text}</p>
                <p><strong>New Status:</strong> <span style="color: #388e3c; font-weight: bold;">{commitment.status.value}</span></p>
                <p><strong>Target Date:</strong> {commitment.target_date}</p>
                {f'<p><strong>Completed Date:</strong> {commitment.completed_at.date()}</p>' if commitment.completed_at else ''}
            </div>
            
            <p>The commitment status has been successfully updated.</p>
            <p><a href="{current_app.config.get('SERVER_URL', '')}/review" style="background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">View Details</a></p>
            """
        
        # Text version (simplified)
        text_body = f"""
        Commitment {commitment.id} - {notification_type.title()}
        
        Query ID: {query.query_id if query else 'N/A'}
        State: {query.state_name if query else 'N/A'}
        Commitment: {commitment.commitment_text}
        Due Date: {commitment.target_date}
        Status: {commitment.status.value}
        
        Please review this commitment in the AMS portal.
        """
        
        return subject, html_body, text_body
    
    def send_batch_commitment_notifications(self, commitments: List[Commitment], 
                                         notification_type: str) -> Dict:
        """Send batch notifications for multiple commitments"""
        results = {
            'total': len(commitments),
            'sent': 0,
            'failed': 0,
            'failed_ids': []
        }
        
        for commitment in commitments:
            success = self.send_commitment_notification(commitment, notification_type)
            if success:
                results['sent'] += 1
            else:
                results['failed'] += 1
                results['failed_ids'].append(commitment.id)
        
        current_app.logger.info(f"Batch notification results: {results}")
        return results
    
    def send_daily_commitment_digest(self) -> bool:
        """Send daily digest of all commitment activities"""
        if not self.enabled:
            return False
        
        try:
            today = datetime.now().date()
            
            # Get commitment statistics
            total_commitments = Commitment.query.count()
            overdue_count = Commitment.query.filter(
                Commitment.target_date < today,
                Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
            ).count()
            
            upcoming_count = Commitment.query.filter(
                Commitment.target_date.between(today, today + timedelta(days=self.reminder_days)),
                Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
            ).count()
            
            completed_today = Commitment.query.filter(
                Commitment.status == CommitmentStatus.completed,
                db.func.date(Commitment.completed_at) == today
            ).count()
            
            # Get admin users
            admin_users = User.query.filter_by(role='admin').all()
            if not admin_users:
                return False
            
            # Prepare digest content
            subject = f"Daily Commitment Digest - {today.strftime('%Y-%m-%d')}"
            
            html_body = f"""
            <h2>Daily Commitment Digest</h2>
            <p>Summary of commitment activities as of {today.strftime('%B %d, %Y')}:</p>
            
            <div style="display: flex; gap: 20px; margin: 20px 0;">
                <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; flex: 1;">
                    <h3 style="margin: 0; color: #1976d2;">Total Commitments</h3>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">{total_commitments}</p>
                </div>
                
                <div style="background-color: #ffebee; padding: 15px; border-radius: 8px; flex: 1;">
                    <h3 style="margin: 0; color: #d32f2f;">Overdue</h3>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #d32f2f;">{overdue_count}</p>
                </div>
                
                <div style="background-color: #fff3e0; padding: 15px; border-radius: 8px; flex: 1;">
                    <h3 style="margin: 0; color: #f57c00;">Upcoming</h3>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #f57c00;">{upcoming_count}</p>
                </div>
                
                <div style="background-color: #e8f5e8; padding: 15px; border-radius: 8px; flex: 1;">
                    <h3 style="margin: 0; color: #388e3c;">Completed Today</h3>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #388e3c;">{completed_today}</p>
                </div>
            </div>
            
            <p><a href="{current_app.config.get('SERVER_URL', '')}/review" style="background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">View Full Dashboard</a></p>
            """
            
            text_body = f"""
            Daily Commitment Digest - {today.strftime('%Y-%m-%d')}
            
            Total Commitments: {total_commitments}
            Overdue: {overdue_count}
            Upcoming (next {self.reminder_days} days): {upcoming_count}
            Completed Today: {completed_today}
            
            Visit the AMS portal for detailed information.
            """
            
            # Send to all admins
            for admin in admin_users:
                if admin.email:
                    msg = Message(
                        subject=subject,
                        recipients=[admin.email],
                        html=html_body,
                        body=text_body,
                        sender=current_app.config.get('MAIL_DEFAULT_SENDER')
                    )
                    mail.send(msg)
            
            current_app.logger.info(f"Daily digest sent to {len(admin_users)} admin users")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to send daily digest: {str(e)}")
            return False
    
    def send_query_assignment_notification(self, query: AuditQuery, assigned_to: str, 
                                        assigned_by: str) -> bool:
        """Send notification when a query is assigned to an official"""
        if not self.enabled:
            return False
        
        try:
            # Find user to notify
            user = User.query.filter(
                (User.username.ilike(f"%{assigned_to}%")) | 
                (User.email.ilike(f"%{assigned_to}%"))
            ).first()
            
            if not user or not user.email:
                current_app.logger.warning(f"No user found for assignment notification: {assigned_to}")
                return False
            
            subject = f"New Query Assigned: {query.query_id}"
            
            html_body = f"""
            <h2>New Query Assignment</h2>
            <p>You have been assigned a new audit query:</p>
            
            <div style="background-color: #e3f2fd; padding: 15px; border-left: 4px solid #1976d2; margin: 15px 0;">
                <h3>Query Details:</h3>
                <p><strong>Query ID:</strong> {query.query_id}</p>
                <p><strong>State:</strong> {query.state_name}</p>
                <p><strong>Date Received:</strong> {query.date_received}</p>
                <p><strong>Priority:</strong> {query.priority}</p>
                <p><strong>Description:</strong> {query.query_description[:200]}{'...' if len(query.query_description) > 200 else ''}</p>
                <p><strong>Assigned By:</strong> {assigned_by}</p>
            </div>
            
            <p>Please review and respond to this query at your earliest convenience.</p>
            <p><a href="{current_app.config.get('SERVER_URL', '')}/pending" style="background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">View Query</a></p>
            """
            
            text_body = f"""
            New Query Assignment
            
            Query ID: {query.query_id}
            State: {query.state_name}
            Date Received: {query.date_received}
            Priority: {query.priority}
            Description: {query.query_description[:200]}{'...' if len(query.query_description) > 200 else ''}
            Assigned By: {assigned_by}
            
            Please review this query in the AMS portal.
            """
            
            msg = Message(
                subject=subject,
                recipients=[user.email],
                html=html_body,
                body=text_body,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            
            mail.send(msg)
            
            current_app.logger.info(f"Assignment notification sent to {user.email} for query {query.query_id}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to send assignment notification: {str(e)}")
            return False
    
    def create_future_issue_notification(self, issue: FutureIssueTracker, message: str = None) -> bool:
        """Create notification when a future issue is resolved"""
        try:
            # Get users to notify (admin, reviewer, and the user who created the draft)
            recipients = []
            
            # Add admin and reviewer users
            admin_users = User.query.filter(User.role.in_(['admin', 'reviewer'])).all()
            recipients.extend([user.email for user in admin_users])
            
            # Add the user who created the original draft
            if issue.related_draft_id:
                draft = DraftFAQ.query.get(issue.related_draft_id)
                if draft and draft.created_by:
                    recipients.append(draft.created_by)
            
            # Remove duplicates
            recipients = list(set(recipients))
            
            # Create notifications for each recipient
            for email in recipients:
                notification = Notification(
                    user_email=email,
                    title=f"Future Issue Resolved - Version {issue.version_fixed}",
                    message=message or f"The future issue related to '{issue.description[:100]}...' has been resolved in version {issue.version_fixed}. A new reply or note has been provided.",
                    notification_type='success',
                    related_issue_id=issue.id,
                    related_draft_id=issue.related_draft_id
                )
                db.session.add(notification)
            
            db.session.commit()
            current_app.logger.info(f"Created future issue notifications for {len(recipients)} users")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to create future issue notification: {str(e)}")
            db.session.rollback()
            return False
    
    def get_user_notifications(self, user_email: str, unread_only: bool = False) -> List[Notification]:
        """Get notifications for a specific user"""
        try:
            query = Notification.query.filter(Notification.user_email == user_email)
            
            if unread_only:
                query = query.filter(Notification.is_read == False)
            
            return query.order_by(Notification.created_at.desc()).limit(50).all()
            
        except Exception as e:
            current_app.logger.error(f"Failed to get user notifications: {str(e)}")
            return []
    
    def mark_notification_read(self, notification_id: int, user_email: str) -> bool:
        """Mark a notification as read"""
        try:
            notification = Notification.query.filter(
                Notification.id == notification_id,
                Notification.user_email == user_email
            ).first()
            
            if notification:
                notification.mark_as_read()
                return True
            else:
                return False
                
        except Exception as e:
            current_app.logger.error(f"Failed to mark notification as read: {str(e)}")
            return False
    
    def get_unread_count(self, user_email: str) -> int:
        """Get count of unread notifications for a user"""
        try:
            return Notification.query.filter(
                Notification.user_email == user_email,
                Notification.is_read == False
            ).count()
        except Exception as e:
            current_app.logger.error(f"Failed to get unread notification count: {str(e)}")
            return 0
