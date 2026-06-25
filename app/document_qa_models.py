import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, LargeBinary, Float, Index
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from cryptography.fernet import Fernet
import hashlib
import hmac
from . import db


class DocumentStatus(enum.Enum):
    uploading = 'uploading'
    processing = 'processing'
    ready = 'ready'
    failed = 'failed'
    deleted = 'deleted'


class DocumentAccessLevel(enum.Enum):
    private = 'private'
    shared = 'shared'


class SecureDocument(db.Model):
    """Secure document storage with user isolation"""
    __tablename__ = 'secure_documents'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Document metadata
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)  # UUID-based filename
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=False)  # Size in bytes
    mime_type = Column(String(100), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hash
    
    # Document processing status
    status = Column(db.Enum(DocumentStatus), default=DocumentStatus.uploading, nullable=False, index=True)
    processing_error = Column(Text, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    
    # Access control
    access_level = Column(db.Enum(DocumentAccessLevel), default=DocumentAccessLevel.private, nullable=False)
    is_encrypted = Column(Boolean, default=True, nullable=False)
    encryption_key_hash = Column(String(64), nullable=True)  # Hash of encryption key for verification
    
    # Document content analysis
    page_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    extracted_text_length = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship('User', backref=db.backref('secure_documents', lazy='dynamic', cascade='all, delete-orphan'))
    chunks = relationship('QADocumentChunk', backref='document', lazy='dynamic', cascade='all, delete-orphan')
    qa_sessions = relationship('QASession', backref='document', lazy='dynamic', cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        Index('idx_document_user_status', 'user_id', 'status'),
        Index('idx_document_created_at', 'created_at'),
        Index('idx_document_file_hash', 'file_hash'),
    )
    
    def generate_secure_filename(self):
        """Generate a secure UUID-based filename"""
        return f"{uuid.uuid4().hex}{self.get_file_extension()}"
    
    def get_file_extension(self):
        """Extract file extension from original filename"""
        if '.' in self.original_filename:
            return '.' + self.original_filename.rsplit('.', 1)[1].lower()
        return ''
    
    def calculate_file_hash(self, file_content):
        """Calculate SHA-256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()
    
    def soft_delete(self):
        """Soft delete the document"""
        self.deleted_at = datetime.utcnow()
        self.status = DocumentStatus.deleted
    
    def __repr__(self):
        return f'<SecureDocument {self.original_filename} (User: {self.user_id})>'


class QADocumentChunk(db.Model):
    """Document chunks for Q&A system - separate from existing DocumentChunk"""
    __tablename__ = 'qa_document_chunks'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('secure_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Chunk content
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Order within document
    page_number = Column(Integer, nullable=True)  # Page number if applicable
    
    # Vector embedding
    embedding = Column(Vector(384), nullable=False)  # Using MiniLM-L6-v2 dimension
    
    # Metadata
    chunk_type = Column(String(50), default='text', nullable=False)  # text, table, image_caption
    confidence_score = Column(Float, nullable=True)  # OCR confidence if applicable
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship('User', backref=db.backref('qa_document_chunks', lazy='dynamic', cascade='all, delete-orphan'))
    
    # Indexes
    __table_args__ = (
        Index('idx_qa_chunk_document_user', 'document_id', 'user_id'),
        Index('idx_qa_chunk_index', 'document_id', 'chunk_index'),
    )
    
    def __repr__(self):
        return f'<QADocumentChunk {self.id} (Doc: {self.document_id}, Index: {self.chunk_index})>'


class QASession(db.Model):
    """Q&A session for a document"""
    __tablename__ = 'qa_sessions'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('secure_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Session metadata
    session_name = Column(String(255), nullable=True)
    session_token = Column(String(64), unique=True, nullable=False, index=True)  # For secure access
    
    # Session statistics
    question_count = Column(Integer, default=0, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship('User', backref=db.backref('qa_sessions', lazy='dynamic', cascade='all, delete-orphan'))
    conversations = relationship('QAConversation', backref='session', lazy='dynamic', cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        Index('idx_session_document_user', 'document_id', 'user_id'),
        Index('idx_session_token', 'session_token'),
        Index('idx_session_last_activity', 'last_activity_at'),
    )
    
    def generate_session_token(self):
        """Generate secure session token"""
        self.session_token = hashlib.sha256(f"{self.id}{self.user_id}{datetime.utcnow().isoformat()}".encode()).hexdigest()
        return self.session_token
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity_at = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<QASession {self.id} (Doc: {self.document_id}, User: {self.user_id})>'


class QAConversation(db.Model):
    """Individual Q&A conversations within a session"""
    __tablename__ = 'qa_conversations'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('qa_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Question and answer
    question = Column(Text, nullable=False)
    question_embedding = Column(Vector(384), nullable=False)  # For similarity search
    
    answer = Column(Text, nullable=False)
    answer_sources = Column(Text, nullable=True)  # JSON string of source chunks
    
    # Response metadata
    confidence_score = Column(Float, nullable=True)
    response_time_ms = Column(Integer, nullable=True)  # Time taken to generate response
    model_used = Column(String(100), nullable=True)  # LLM model used
    
    # Source context
    relevant_chunks = Column(Text, nullable=True)  # JSON string of chunk IDs used
    context_length = Column(Integer, nullable=True)  # Total context characters used
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship('User', backref=db.backref('qa_conversations', lazy='dynamic', cascade='all, delete-orphan'))
    
    # Indexes
    __table_args__ = (
        Index('idx_conversation_session_user', 'session_id', 'user_id'),
        Index('idx_conversation_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f'<QAConversation {self.id} (Session: {self.session_id})>'


class DocumentAccessLog(db.Model):
    """Audit log for document access"""
    __tablename__ = 'document_access_logs'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('secure_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Access details
    action = Column(String(50), nullable=False)  # upload, view, download, delete, query
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Additional context
    session_id = Column(String(64), nullable=True)
    additional_data = Column(Text, nullable=True)  # JSON string for additional context
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship('User', backref=db.backref('document_access_logs', lazy='dynamic', cascade='all, delete-orphan'))
    document = relationship('SecureDocument', backref=db.backref('access_logs', lazy='dynamic', cascade='all, delete-orphan'))
    
    # Indexes
    __table_args__ = (
        Index('idx_access_document_user', 'document_id', 'user_id'),
        Index('idx_access_action', 'action'),
        Index('idx_access_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f'<DocumentAccessLog {self.action} (Doc: {self.document_id}, User: {self.user_id})>'


class DocumentShare(db.Model):
    """Document sharing between users"""
    __tablename__ = 'document_shares'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('secure_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    shared_by_user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    shared_with_user_id = Column(Integer, ForeignKey('user.id', ondelete='CASCADE'), nullable=True, index=True)
    
    # Share details
    share_token = Column(String(64), unique=True, nullable=False, index=True)
    permission_level = Column(String(20), default='view', nullable=False)  # view, query
    
    # Share constraints
    expires_at = Column(DateTime, nullable=True)
    max_queries = Column(Integer, nullable=True)
    query_count = Column(Integer, default=0, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    shared_by_user = relationship('User', foreign_keys=[shared_by_user_id], backref=db.backref('shared_documents', lazy='dynamic', cascade='all, delete-orphan'))
    shared_with_user = relationship('User', foreign_keys=[shared_with_user_id], backref=db.backref('received_shares', lazy='dynamic', cascade='all, delete-orphan'))
    document = relationship('SecureDocument', backref=db.backref('shares', lazy='dynamic', cascade='all, delete-orphan'))
    
    # Indexes
    __table_args__ = (
        Index('idx_share_document_shared_by', 'document_id', 'shared_by_user_id'),
        Index('idx_share_token', 'share_token'),
        Index('idx_share_active', 'is_active', 'expires_at'),
    )
    
    def generate_share_token(self):
        """Generate secure share token"""
        self.share_token = hashlib.sha256(f"{self.document_id}{self.shared_by_user_id}{datetime.utcnow().isoformat()}".encode()).hexdigest()
        return self.share_token
    
    def is_valid(self):
        """Check if share is valid and not expired"""
        if not self.is_active or self.revoked_at:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.max_queries and self.query_count >= self.max_queries:
            return False
        return True
    
    def increment_query_count(self):
        """Increment query count"""
        self.query_count += 1
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<DocumentShare {self.id} (Doc: {self.document_id}, By: {self.shared_by_user_id})>'
