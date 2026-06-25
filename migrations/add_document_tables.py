#!/usr/bin/env python3
"""
Migration script to add document management tables to the database.

This script creates the necessary tables for the document understanding module:
- document: Main document storage
- document_chunk: Text chunks for vector search
- document_audit_log: Security audit trail
- compliance_log: GDPR compliance tracking
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app, db
from app.document_models import Document, DocumentChunk, DocumentAuditLog, ComplianceLog


def create_document_tables():
    """Create document management tables if they don't exist."""
    
    app = create_app()
    with app.app_context():
        print("Creating document management tables...")
        
        try:
            # Create all document-related tables
            db.create_all()
            
            # Check if tables were created successfully
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            required_tables = [
                'document',
                'document_chunk', 
                'document_audit_log',
                'compliance_log'
            ]
            
            print("\nTable creation status:")
            all_created = True
            for table in required_tables:
                exists = table in existing_tables
                status = "✅ CREATED" if exists else "❌ FAILED"
                print(f"  - {table}: {status}")
                if not exists:
                    all_created = False
            
            if all_created:
                print("\n✅ All document tables created successfully!")
                
                # Create pgvector extension if not exists
                try:
                    db.session.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    db.session.commit()
                    print("✅ pgvector extension enabled")
                except Exception as e:
                    print(f"⚠️  pgvector extension issue: {e}")
                    print("   Make sure PostgreSQL has pgvector extension installed")
                
            else:
                print("\n❌ Some tables failed to create")
                return False
                
        except Exception as e:
            print(f"\n❌ Error creating tables: {e}")
            db.session.rollback()
            return False
        
        return True


def verify_table_structure():
    """Verify that table structure is correct."""
    app = create_app()
    with app.app_context():
        print("\nVerifying table structure...")
        
        try:
            # Check document table structure
            inspector = db.inspect(db.engine)
            
            # Document table
            doc_columns = [col['name'] for col in inspector.get_columns('document')]
            expected_doc_cols = {
                'id', 'user_id', 'session_id', 'original_filename', 'safe_filename',
                'file_size', 'mime_type', 'chunk_count', 'has_injection_attempt',
                'upload_time', 'content_hash', 'encrypted_content', 'created_at', 'updated_at'
            }
            
            print("Document table columns:")
            for col in expected_doc_cols:
                exists = col in doc_columns
                status = "✅" if exists else "❌"
                print(f"  - {col}: {status}")
            
            # Document chunk table
            chunk_columns = [col['name'] for col in inspector.get_columns('document_chunk')]
            expected_chunk_cols = {
                'id', 'document_id', 'chunk_index', 'content', 'content_hash',
                'is_flagged', 'flagged_patterns', 'created_at'
            }
            
            print("\nDocument chunk table columns:")
            for col in expected_chunk_cols:
                exists = col in chunk_columns
                status = "✅" if exists else "❌"
                print(f"  - {col}: {status}")
            
            print("\n✅ Table structure verification complete")
            
        except Exception as e:
            print(f"❌ Error verifying structure: {e}")
            return False
        
        return True


def main():
    """Main migration function."""
    print("=== Document Tables Migration ===\n")
    
    # Create tables
    if create_document_tables():
        # Verify structure
        verify_table_structure()
        
        print("\n=== Migration Complete ===")
        print("✅ Document management system is ready")
        print("\nNext steps:")
        print("1. Restart your Flask application")
        print("2. Test document upload functionality")
        print("3. Verify encryption/decryption works")
    else:
        print("\n=== Migration Failed ===")
        print("❌ Please check the error messages above")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMigration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
