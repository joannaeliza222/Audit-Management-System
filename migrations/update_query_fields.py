#!/usr/bin/env python3
"""
Database migration script to update FAQ and DraftFAQ models
Changes:
- Replace 'question' field with 'subject' and 'query_description' fields
- Add 'query_date' field
- Update 'norm_question' to 'norm_query'
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text

def migrate_models():
    """Update database schema to use new field structure"""
    app = create_app()
    
    with app.app_context():
        try:
            print("Starting migration to update query fields...")
            
            # Add new columns to FAQ table
            print("Adding new columns to FAQ table...")
            db.session.execute(text("""
                ALTER TABLE faq 
                ADD COLUMN IF NOT EXISTS subject VARCHAR(500),
                ADD COLUMN IF NOT EXISTS query_description TEXT,
                ADD COLUMN IF NOT EXISTS query_date DATE,
                ADD COLUMN IF NOT EXISTS norm_query VARCHAR(1024)
            """))
            
            # Add new columns to DraftFAQ table  
            print("Adding new columns to DraftFAQ table...")
            db.session.execute(text("""
                ALTER TABLE draftfaq 
                ADD COLUMN IF NOT EXISTS subject VARCHAR(500),
                ADD COLUMN IF NOT EXISTS query_description TEXT,
                ADD COLUMN IF NOT EXISTS query_date DATE,
                ADD COLUMN IF NOT EXISTS norm_query VARCHAR(1024)
            """))
            
            # Migrate data from question to new fields
            print("Migrating data from question to new fields...")
            
            # For FAQ table
            db.session.execute(text("""
                UPDATE faq 
                SET subject = LEFT(question, 200),
                    query_description = question,
                    norm_query = norm_question
                WHERE subject IS NULL
            """))
            
            # For DraftFAQ table
            db.session.execute(text("""
                UPDATE draftfaq 
                SET subject = LEFT(question, 200),
                    query_description = question,
                    norm_query = norm_question
                WHERE subject IS NULL
            """))
            
            # Set query_date from timestamp if not set
            db.session.execute(text("""
                UPDATE faq SET query_date = DATE(timestamp) WHERE query_date IS NULL
            """))
            
            db.session.execute(text("""
                UPDATE draftfaq SET query_date = DATE(created_at) WHERE query_date IS NULL
            """))
            
            db.session.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            db.session.rollback()
            raise

if __name__ == "__main__":
    migrate_models()
