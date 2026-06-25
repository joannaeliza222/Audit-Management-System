#!/usr/bin/env python3
"""
Script to update SQLAlchemy model definitions to include new fields
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def update_models_file():
    """Update models.py to include new field definitions"""
    
    models_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'models.py')
    
    # Read the current models.py file
    with open(models_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Update FAQ model
    faq_old = '''class FAQ(db.Model):
    __tablename__ = 'faq'
    id = db.Column(db.Integer, primary_key=True, comment="Primary key")
    question = db.Column(db.Text, nullable=False, comment="Question entered by user")
    norm_question = db.Column(db.String(1024), nullable=False, index=True,
                              comment="Normalized lowercased question for uniqueness")
    reply = db.Column(db.Text, nullable=True, comment="Reply/answer mapped to the question")
    memo_id = db.Column(db.String(128), nullable=True, comment="Optional memo ID or reference number")
    state_name = db.Column(db.String(100), nullable=True, index=True, comment="State name to separate questions")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, comment="Timestamp when the question was added")
    embedding = db.Column(db.LargeBinary, comment="Embedding vector - stored as bytea for compatibility")
    __table_args__ = (UniqueConstraint('norm_question', 'state_name', name='uq_question_state'),)'''
    
    faq_new = '''class FAQ(db.Model):
    __tablename__ = 'faq'
    id = db.Column(db.Integer, primary_key=True, comment="Primary key")
    subject = db.Column(db.String(500), nullable=False, comment="Subject of the query")
    query_description = db.Column(db.Text, nullable=False, comment="Detailed query description")
    norm_query = db.Column(db.String(1024), nullable=False, index=True,
                              comment="Normalized lowercased query for uniqueness")
    reply = db.Column(db.Text, nullable=True, comment="Reply/answer mapped to query")
    memo_id = db.Column(db.String(128), nullable=True, comment="Optional memo ID or reference number")
    state_name = db.Column(db.String(100), nullable=True, index=True, comment="State name to separate queries")
    query_date = db.Column(db.Date, nullable=True, comment="Date when query was created")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, comment="Timestamp when query was added")
    embedding = db.Column(db.LargeBinary, comment="Embedding vector - stored as bytea for compatibility")
    __table_args__ = (UniqueConstraint('norm_query', 'state_name', name='uq_query_state'),)'''
    
    # Update DraftFAQ model
    draft_faq_old = '''class DraftFAQ(db.Model):
    __tablename__ = 'draftfaq'
    id = db.Column(db.Integer, primary_key=True, comment="Primary key")
    original_id = db.Column(db.Integer, db.ForeignKey('faq.id', ondelete='SET NULL'), nullable=True)
    question = db.Column(db.Text, nullable=False, comment="Question entered by user")
    norm_question = db.Column(db.String(1024), nullable=False, index=True,
                              comment="Normalized lowercased question for uniqueness")
    reply = db.Column(db.Text, comment="Reply/answer mapped to the question")
    memo_id = db.Column(db.String(128), nullable=True, comment="Optional memo ID or reference number")
    state_name = db.Column(db.String(100), nullable=True, index=True, comment="State name to separate questions")
    status = db.Column(db.Enum(DraftStatus), default=DraftStatus.pending, nullable=False, index=True)
    created_by = db.Column(db.String(120), comment="User who entered/uploaded the question")
    modified_by = db.Column(db.String(120), comment="User who modified the reply")
    approved_by = db.Column(db.String(120), comment="User who merged the question to FAQ table")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment="Timestamp when the question entered/uploaded")
    modified_at = db.Column(db.DateTime, comment="Timestamp when the reply was modified")
    approved_at = db.Column(db.DateTime, comment="Timestamp when the question was merged to FAQ table")
    embedding = db.Column(db.LargeBinary, comment="Embedding vector - stored as bytea for compatibility")
    __table_args__ = (UniqueConstraint('norm_question', 'state_name', name='uq_draft_question_state'),)'''
    
    draft_faq_new = '''class DraftFAQ(db.Model):
    __tablename__ = 'draftfaq'
    id = db.Column(db.Integer, primary_key=True, comment="Primary key")
    original_id = db.Column(db.Integer, db.ForeignKey('faq.id', ondelete='SET NULL'), nullable=True)
    subject = db.Column(db.String(500), nullable=False, comment="Subject of the query")
    query_description = db.Column(db.Text, nullable=False, comment="Detailed query description")
    norm_query = db.Column(db.String(1024), nullable=False, index=True,
                              comment="Normalized lowercased query for uniqueness")
    reply = db.Column(db.Text, comment="Reply/answer mapped to query")
    memo_id = db.Column(db.String(128), nullable=True, comment="Optional memo ID or reference number")
    state_name = db.Column(db.String(100), nullable=True, index=True, comment="State name to separate queries")
    query_date = db.Column(db.Date, nullable=True, comment="Date when query was created")
    status = db.Column(db.Enum(DraftStatus), default=DraftStatus.pending, nullable=False, index=True)
    created_by = db.Column(db.String(120), comment="User who entered/uploaded the query")
    modified_by = db.Column(db.String(120), comment="User who modified the reply")
    approved_by = db.Column(db.String(120), comment="User who merged the query to FAQ table")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment="Timestamp when the query entered/uploaded")
    modified_at = db.Column(db.DateTime, comment="Timestamp when the reply was modified")
    approved_at = db.Column(db.DateTime, comment="Timestamp when the query was merged to FAQ table")
    embedding = db.Column(db.LargeBinary, comment="Embedding vector - stored as bytea for compatibility")
    __table_args__ = (UniqueConstraint('norm_query', 'state_name', name='uq_draft_query_state'),)'''
    
    # Replace the content
    content = content.replace(faq_old, faq_new)
    content = content.replace(draft_faq_old, draft_faq_new)
    
    # Write the updated content back to the file
    with open(models_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully updated models.py with new field definitions")

if __name__ == "__main__":
    update_models_file()
