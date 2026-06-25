#!/usr/bin/env python3
"""
Test script for AMS notification system
Run this script to test email notifications and commitment tracking
"""

import os
import sys
import secrets
from datetime import datetime, timedelta
from email.message import Message

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from app import create_app, db
from app.audit_models import AuditQuery, Commitment, CommitmentStatus, AuditQueryStatus
from app.services.commitment_tracker import CommitmentTracker
from app.services.notification_service import NotificationService
from app.models import User


def create_test_data():
    """Create test data for notification testing"""
    print("Creating test data...")
    
    # Create test user if not exists
    test_user = User.query.filter_by(username='Admin').first()
    if not test_user:
        test_user = User(
            username='Admin',
            email='ejoanna222@gmail.com',
            role='admin'
        )
        test_user.set_password(os.getenv('TEST_USER_PASSWORD', secrets.token_urlsafe(16)))
        db.session.add(test_user)
        db.session.commit()
        print(f"Created test user: {test_user.username}")
    
    # Create test audit query
    test_query = AuditQuery(
        query_id='TEST-001',
        state_name='TN',
        query_description='This is a test query for notification testing',
        assigned_official='Test Official',
        assigned_official_email='ejoanna222@gmail.com',
        status=AuditQueryStatus.responded,
        response_provided='This issue will be rectified in the next update.',
        response_date=datetime.now().date(),
        date_received=datetime.now().date() - timedelta(days=5)
    )
    db.session.add(test_query)
    db.session.commit()
    print(f"Created test query: {test_query.query_id}")
    
    # Create overdue commitment
    overdue_commitment = Commitment(
        audit_query_id=test_query.id,
        commitment_text='This commitment will be rectified in the next update',
        commitment_type='rectification',
        target_date=datetime.now().date() - timedelta(days=2),  # 2 days overdue
        status=CommitmentStatus.pending,
        detected_at=datetime.now() - timedelta(days=10)
    )
    db.session.add(overdue_commitment)
    db.session.commit()
    print(f"Created overdue commitment: {overdue_commitment.id}")
    
    # Create upcoming commitment
    upcoming_commitment = Commitment(
        audit_query_id=test_query.id,
        commitment_text='This feature will be implemented in the upcoming release',
        commitment_type='implementation',
        target_date=datetime.now().date() + timedelta(days=3),  # 3 days from now
        status=CommitmentStatus.in_progress,
        detected_at=datetime.now() - timedelta(days=5)
    )
    db.session.add(upcoming_commitment)
    db.session.commit()
    print(f"Created upcoming commitment: {upcoming_commitment.id}")
    
    return test_user, test_query, overdue_commitment, upcoming_commitment


def test_notification_service():
    """Test the notification service"""
    print("\n" + "="*50)
    print("TESTING NOTIFICATION SERVICE")
    print("="*50)
    
    app = create_app('development')
    
    with app.app_context():
        # Create test data
        test_user, test_query, overdue_commitment, upcoming_commitment = create_test_data()
        
        # Initialize notification service
        notification_service = NotificationService()
        
        # Test overdue notification
        print("\n1. Testing overdue commitment notification...")
        success = notification_service.send_commitment_notification(
            overdue_commitment, 'overdue'
        )
        print(f"   Overdue notification sent: {success}")
        
        # Test upcoming notification
        print("\n2. Testing upcoming commitment notification...")
        success = notification_service.send_commitment_notification(
            upcoming_commitment, 'upcoming'
        )
        print(f"   Upcoming notification sent: {success}")
        
        # Test status update notification
        print("\n3. Testing status update notification...")
        upcoming_commitment.status = CommitmentStatus.completed
        upcoming_commitment.completed_at = datetime.now()
        db.session.commit()
        
        success = notification_service.send_commitment_notification(
            upcoming_commitment, 'status_update'
        )
        print(f"   Status update notification sent: {success}")
        
        # Test daily digest
        print("\n4. Testing daily digest...")
        success = notification_service.send_daily_commitment_digest()
        print(f"   Daily digest sent: {success}")
        
        # Test query assignment notification
        print("\n5. Testing query assignment notification...")
        new_query = AuditQuery(
            query_id='TEST-002',
            state_name='TN',
            query_description='Another test query for assignment',
            assigned_official='Admin',
            date_received=datetime.now().date()
        )
        db.session.add(new_query)
        db.session.commit()
        
        success = notification_service.send_query_assignment_notification(
            new_query, 'test_admin', 'system'
        )
        print(f"   Assignment notification sent: {success}")


def test_commitment_tracker():
    """Test the commitment tracker service"""
    print("\n" + "="*50)
    print("TESTING COMMITMENT TRACKER")
    print("="*50)
    
    app = create_app('development')
    
    with app.app_context():
        tracker = CommitmentTracker()
        
        # Test dashboard data
        print("\n1. Testing dashboard data generation...")
        dashboard_data = tracker.get_commitment_dashboard_data()
        print(f"   Total commitments: {dashboard_data['total_commitments']}")
        print(f"   Overdue commitments: {dashboard_data['overdue_count']}")
        print(f"   Completion rate: {dashboard_data['completion_rate_90_days']}%")
        
        # Test overdue commitments
        print("\n2. Testing overdue commitments retrieval...")
        overdue = tracker.get_overdue_commitments()
        print(f"   Found {len(overdue)} overdue commitments")
        for commitment in overdue:
            print(f"   - {commitment.id}: {commitment.commitment_text[:50]}...")
        
        # Test upcoming commitments
        print("\n3. Testing upcoming commitments retrieval...")
        upcoming = tracker.get_upcoming_commitments(days_ahead=7)
        print(f"   Found {len(upcoming)} upcoming commitments")
        for commitment in upcoming:
            days_until = (commitment.target_date - datetime.now().date()).days
            print(f"   - {commitment.id}: {days_until} days until due")
        
        # Test commitment detection from response
        print("\n4. Testing commitment detection...")
        test_response = "This issue will be rectified in the next update scheduled for 15-12-2024. The feature will be implemented within 30 days."
        commitments = tracker.detect_commitments_from_response(1, test_response)
        print(f"   Detected {len(commitments)} commitments from response")
        for commitment in commitments:
            print(f"   - {commitment.commitment_text[:50]}... (Due: {commitment.target_date})")
        
        # Test bulk notifications
        print("\n5. Testing bulk notifications...")
        notifications_sent = tracker.send_commitment_notifications()
        print(f"   Sent {notifications_sent} notifications")


def test_email_configuration():
    """Test email configuration"""
    print("\n" + "="*50)
    print("TESTING EMAIL CONFIGURATION")
    print("="*50)
    
    app = create_app('development')
    
    with app.app_context():
        # Check email configuration
        mail_config = {
            'server': app.config.get('MAIL_SERVER'),
            'port': app.config.get('MAIL_PORT'),
            'use_tls': app.config.get('MAIL_USE_TLS'),
            'use_ssl': app.config.get('MAIL_USE_SSL'),
            'username': app.config.get('MAIL_USERNAME'),
            'sender': app.config.get('MAIL_DEFAULT_SENDER'),
            'enabled': app.config.get('NOTIFICATION_ENABLED')
        }
        
        print("Email Configuration:")
        for key, value in mail_config.items():
            if key == 'password':
                print(f"   {key}: {'*' * len(str(value)) if value else 'Not set'}")
            else:
                print(f"   {key}: {value}")
        
        # Test email connection
        if mail_config['server'] and mail_config['username']:
            print("\nTesting email connection...")
            try:
                from flask_mail import Mail
                mail = Mail(app)
                
                # Try to send a test email
                msg = Message(
                    'AMS Email Test',
                    recipients=[mail_config['username']],
                    body='This is a test email from AMS notification system.',
                    sender=mail_config['sender']
                )
                
                mail.send(msg)
                print("   ✓ Email sent successfully!")
                
            except Exception as e:
                print(f"   ✗ Email test failed: {str(e)}")
        else:
            print("   ⚠ Email not configured - skipping connection test")


def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "="*50)
    print("CLEANING UP TEST DATA")
    print("="*50)
    
    app = create_app('development')
    
    with app.app_context():
        # Remove test commitments
        Commitment.query.filter(Commitment.commitment_text.like('%test%')).delete()
        
        # Remove test queries
        AuditQuery.query.filter(AuditQuery.query_id.like('TEST-%')).delete()
        
        # Remove test user
        User.query.filter_by(username='test_admin').delete()
        
        db.session.commit()
        print("Test data cleaned up successfully")


def main():
    """Main test function"""
    print("AMS Notification System Test Suite")
    print("=" * 50)
    
    try:
        # Test email configuration first
        test_email_configuration()
        
        # Test notification service
        test_notification_service()
        
        # Test commitment tracker
        test_commitment_tracker()
        
        print("\n" + "="*50)
        print("ALL TESTS COMPLETED")
        print("="*50)
        
        # Ask if user wants to clean up
        response = input("\nDo you want to clean up test data? (y/n): ").lower().strip()
        if response == 'y':
            cleanup_test_data()
        
        print("\nTest suite completed successfully!")
        
    except Exception as e:
        print(f"\nTest failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
