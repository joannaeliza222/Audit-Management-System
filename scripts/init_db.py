#!/usr/bin/env python3
"""
Database initialization script for AMS
Creates all tables and initial admin user from Tamil Nadu
"""

import os
import sys
import secrets
from datetime import datetime

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, FAQ, DraftFAQ, DataDump, FailedLoginAttempt, Logs
from app.audit_models import AuditQuery, Commitment, QueryVersion, DocumentProcessing, ExtractedItem
from app.utils.passwords import hash_password


def init_database():
    """Initialize database with all tables and create admin user"""
    
    app = create_app()
    
    with app.app_context():
        print("Creating database tables...")
        
        # Create all tables
        db.create_all()
        print("All tables created successfully!")
        
        # Check if admin user already exists
        admin_email = os.getenv('INITIAL_ADMIN_EMAIL', 'admin@example.com')
        existing_admin = User.query.filter_by(email=admin_email).first()
        
        if existing_admin:
            print(f"Admin user {admin_email} already exists!")
            return False
        
        print("Creating initial admin user...")
        
        # Create admin user
        admin_user = User(
            name=os.getenv('INITIAL_ADMIN_NAME', 'Administrator'),
            email=admin_email,
            password=hash_password(os.getenv('INITIAL_ADMIN_PASSWORD', secrets.token_urlsafe(16))),
            role="admin",
            state_name=os.getenv('INITIAL_ADMIN_STATE', 'Default'),
            is_approved=True,
            email_verified=True
        )
        
        db.session.add(admin_user)
        
        # Add initial log entry
        init_log = Logs(
            action="Database initialization",
            user_email=admin_email,
            timestamp=datetime.utcnow()
        )
        db.session.add(init_log)
        
        try:
            db.session.commit()
            print("Admin user created successfully!")
            print(f"   Email: {admin_email}")
            print(f"   Password: Set via INITIAL_ADMIN_PASSWORD environment variable")
            print(f"   Name: {admin_user.name}")
            print(f"   State: {admin_user.state_name}")
            print(f"   Role: admin")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user: {e}")
            return False


def check_database_status():
    """Check database connection and table status"""
    
    app = create_app()
    
    with app.app_context():
        try:
            # Test database connection
            from sqlalchemy import text
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("Database connection successful!")
            
            # Check existing tables
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            print(f"Found {len(tables)} tables:")
            for table in sorted(tables):
                print(f"   - {table}")
            
            # Check admin user
            admin_count = User.query.filter_by(role="admin").count()
            print(f"Found {admin_count} admin user(s)")
            
            return True
            
        except Exception as e:
            print(f"Database connection failed: {e}")
            return False


def create_sample_data():
    """Create sample data for testing (optional)"""
    
    app = create_app()
    
    with app.app_context():
        print("Creating sample FAQ data...")
        
        sample_faqs = [
            {
                "question": "What is the audit process for Tamil Nadu?",
                "reply": "The audit process involves initial review, data collection, analysis, and reporting.",
                "state_name": "Tamil Nadu",
                "memo_id": "TN-AUDIT-001"
            },
            {
                "question": "How to submit audit reports?",
                "reply": "Audit reports should be submitted through the official portal with proper documentation.",
                "state_name": "Tamil Nadu",
                "memo_id": "TN-AUDIT-002"
            }
        ]
        
        for faq_data in sample_faqs:
            # Check if already exists
            existing = FAQ.query.filter_by(
                memo_id=faq_data["memo_id"]
            ).first()
            
            if not existing:
                faq = FAQ(
                    subject=faq_data["question"],
                    norm_query=faq_data["question"].lower().strip(),
                    reply=faq_data["reply"],
                    state_name=faq_data["state_name"],
                    memo_id=faq_data["memo_id"]
                )
                db.session.add(faq)
        
        try:
            db.session.commit()
            print("Sample FAQ data created!")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error creating sample data: {e}")
            return False


if __name__ == "__main__":
    print("AMS Database Initialization Script")
    print("=" * 50)
    
    # Check current status
    print("\nChecking database status...")
    if not check_database_status():
        print("Cannot proceed - database connection failed")
        sys.exit(1)
    
    # Initialize database
    print("\nInitializing database...")
    if init_database():
        print("\nDatabase initialization completed!")
        
        # Optionally create sample data
        create_sample = input("\nCreate sample data? (y/N): ").lower().strip()
        if create_sample in ['y', 'yes']:
            create_sample_data()
        
        print("\nSetup completed successfully!")
        print("You can now login with:")
        print(f"   Email: {admin_email}")
        print("   Password: Set via INITIAL_ADMIN_PASSWORD environment variable")
    else:
        print("\nDatabase initialization failed!")
        sys.exit(1)
