import enum
import uuid
import hashlib
import hmac
from datetime import datetime
from flask import url_for
from pgvector.sqlalchemy import Vector
from sqlalchemy import UniqueConstraint, Text, LargeBinary, Index
from werkzeug.security import check_password_hash
from cryptography.fernet import Fernet
from . import db


class Document(db.Model):
    """Document model with encrypted storage and metadata"""
    __tablename__ = 'documents'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    encrypted_content = db.Column(db.LargeBinary, nullable=False)  # AES-256-GCM encrypted
    content_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA-256 hash
    upload_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    has_injection_attempt = db.Column(db.Boolean, default=False)
    chunk_count = db.Column(db.Integer, default=0)
    
    # Relationship to user
    user = db.relationship('User', backref=db.backref('documents', lazy=True, cascade='all, delete-orphan'))
    
    def encrypt_content(self, content, encryption_key):
        """Encrypt content using AES-256-GCM via Fernet"""
        f = Fernet(encryption_key)
        return f.encrypt(content)
    
    def decrypt_content(self, encryption_key):
        """Decrypt content using AES-256-GCM via Fernet"""
        f = Fernet(encryption_key)
        return f.decrypt(self.encrypted_content)
    
    def generate_content_hash(self, content):
        """Generate SHA-256 hash of content"""
        return hashlib.sha256(content).hexdigest()
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'mime_type': self.mime_type,
            'file_size': self.file_size,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'chunk_count': self.chunk_count,
            'has_injection_attempt': self.has_injection_attempt
        }


class DocumentChunk(db.Model):
    """Document chunks with embeddings for vector search"""
    __tablename__ = 'document_chunks'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    chunk_text = db.Column(db.Text, nullable=False)
    embedding = db.Column(Vector(384), nullable=False)  # pgvector embedding
    flagged = db.Column(db.Boolean, default=False)  # Flagged for injection attempts
    token_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    document = db.relationship('Document', backref=db.backref('chunks', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('document_chunks', lazy=True, cascade='all, delete-orphan'))
    
    __table_args__ = (
        Index('idx_document_user', 'document_id', 'user_id'),
        Index('idx_user_flagged', 'user_id', 'flagged'),
    )
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'user_id': self.user_id,
            'chunk_index': self.chunk_index,
            'chunk_text': self.chunk_text[:500] + '...' if len(self.chunk_text) > 500 else self.chunk_text,
            'flagged': self.flagged,
            'token_count': self.token_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DocumentAuditLog(db.Model):
    """Audit log for document operations"""
    __tablename__ = 'document_audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)  # upload, delete, query, injection_detected
    event_data = db.Column(db.Text)  # JSON string with additional event data
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('document_audit_logs', lazy=True))
    document = db.relationship('Document', backref=db.backref('audit_logs', lazy=True))
    
    __table_args__ = (
        Index('idx_user_event_time', 'user_id', 'event_type', 'timestamp'),
        Index('idx_event_time', 'event_type', 'timestamp'),
    )
    
    @classmethod
    def log_event(cls, user_id, event_type, document_id=None, event_data=None, ip_address=None, user_agent=None):
        """Create an audit log entry"""
        import json
        log_entry = cls(
            user_id=user_id,
            document_id=document_id,
            event_type=event_type,
            event_data=json.dumps(event_data) if event_data else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(log_entry)
        return log_entry
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        import json
        return {
            'id': self.id,
            'user_id': self.user_id,
            'document_id': self.document_id,
            'event_type': self.event_type,
            'event_data': json.loads(self.event_data) if self.event_data else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class ComplianceLog(db.Model):
    """GDPR compliance log for data erasure"""
    __tablename__ = 'compliance_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA-256 hash
    gdpr_token = db.Column(db.String(64), nullable=False, unique=True, index=True)  # HMAC-SHA256 token
    erasure_reason = db.Column(db.String(100), nullable=False)  # gdpr_erasure_request, account_closure
    deletion_timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    documents_deleted = db.Column(db.Integer, default=0)
    chunks_deleted = db.Column(db.Integer, default=0)
    audit_entries_anonymised = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='completed')  # completed, partial_failure
    
    @classmethod
    def generate_user_hash(cls, user_id, audit_salt):
        """Generate SHA-256 hash of user ID with salt"""
        return hashlib.sha256(f"{user_id}{audit_salt}".encode()).hexdigest()
    
    @classmethod
    def generate_gdpr_token(cls, user_id, deletion_timestamp, erasure_secret):
        """Generate HMAC-SHA256 token for GDPR compliance"""
        message = f"{user_id}{deletion_timestamp}".encode()
        return hmac.new(
            erasure_secret.encode(), 
            message, 
            hashlib.sha256
        ).hexdigest()
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'user_id_hash': self.user_id_hash,
            'erasure_reason': self.erasure_reason,
            'deletion_timestamp': self.deletion_timestamp.isoformat() if self.deletion_timestamp else None,
            'documents_deleted': self.documents_deleted,
            'chunks_deleted': self.chunks_deleted,
            'audit_entries_anonymised': self.audit_entries_anonymised,
            'status': self.status
        }
