import enum
from datetime import datetime
from . import db


class AuditQueryStatus(enum.Enum):
    received = 'received'
    in_progress = 'in_progress'
    awaiting_response = 'awaiting_response'
    responded = 'responded'
    closed = 'closed'
    escalated = 'escalated'


class CommitmentStatus(enum.Enum):
    pending = 'pending'
    in_progress = 'in_progress'
    completed = 'completed'
    overdue = 'overdue'
    cancelled = 'cancelled'


class AuditQuery(db.Model):
    __tablename__ = 'audit_query'
    
    id = db.Column(db.Integer, primary_key=True)
    query_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    state_name = db.Column(db.String(100), nullable=False, index=True)
    date_received = db.Column(db.Date, nullable=False, index=True)
    query_description = db.Column(db.Text, nullable=False)
    assigned_official = db.Column(db.String(200), nullable=True)
    assigned_official_email = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(200), nullable=True)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    status = db.Column(db.Enum(AuditQueryStatus), default=AuditQueryStatus.received, nullable=False, index=True)
    
    # Response tracking
    response_provided = db.Column(db.Text, nullable=True)
    response_date = db.Column(db.Date, nullable=True)
    response_method = db.Column(db.String(50), nullable=True)  # email, letter, portal
    
    # Metadata
    source_document = db.Column(db.String(500), nullable=True)  # Original document path
    memo_id = db.Column(db.String(128), nullable=True, index=True)
    audit_year = db.Column(db.Integer, nullable=True, index=True)
    audit_type = db.Column(db.String(100), nullable=True)  # financial, compliance, performance
    
    # Vector search
    embedding = db.Column(db.LargeBinary, comment="Embedding vector stored as bytea (384-dim) for semantic search")
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    commitments = db.relationship("Commitment", backref="audit_query", cascade="all, delete-orphan")
    version_history = db.relationship("QueryVersion", backref="audit_query", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<AuditQuery {self.query_id} - {self.state_name}>'


class Commitment(db.Model):
    __tablename__ = 'commitment'
    
    id = db.Column(db.Integer, primary_key=True)
    audit_query_id = db.Column(db.Integer, db.ForeignKey('audit_query.id', ondelete='CASCADE'), nullable=False)
    
    # Commitment details
    commitment_text = db.Column(db.Text, nullable=False)
    commitment_type = db.Column(db.String(50), nullable=True)  # rectification, implementation, policy_change
    target_date = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.Enum(CommitmentStatus), default=CommitmentStatus.pending, nullable=False, index=True)
    
    # Tracking
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    overdue_notified = db.Column(db.Boolean, default=False)
    
    # Additional context
    responsible_party = db.Column(db.String(200), nullable=True)
    implementation_notes = db.Column(db.Text, nullable=True)
    verification_method = db.Column(db.String(200), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Commitment {self.id} - {self.status.value}>'


class QueryVersion(db.Model):
    __tablename__ = 'query_version'
    
    id = db.Column(db.Integer, primary_key=True)
    audit_query_id = db.Column(db.Integer, db.ForeignKey('audit_query.id', ondelete='CASCADE'), nullable=False)
    
    # Version details
    version_number = db.Column(db.Integer, nullable=False)
    change_type = db.Column(db.String(50), nullable=False)  # created, response_updated, status_changed, reassigned
    
    # State snapshots
    previous_status = db.Column(db.Enum(AuditQueryStatus), nullable=True)
    new_status = db.Column(db.Enum(AuditQueryStatus), nullable=True)
    previous_response = db.Column(db.Text, nullable=True)
    new_response = db.Column(db.Text, nullable=True)
    previous_assigned = db.Column(db.String(200), nullable=True)
    new_assigned = db.Column(db.String(200), nullable=True)
    
    # Change metadata
    changed_by = db.Column(db.String(120), nullable=False)
    change_reason = db.Column(db.Text, nullable=True)
    change_timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Full snapshot for restoration
    full_snapshot = db.Column(db.JSON, nullable=True)
    
    def __repr__(self):
        return f'<QueryVersion {self.audit_query_id} v{self.version_number}>'


class DocumentProcessing(db.Model):
    __tablename__ = 'document_processing'
    
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(500), nullable=False)
    stored_filename = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)  # pdf, xlsx, csv
    file_size = db.Column(db.BigInteger, nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    checksum = db.Column(db.String(64), nullable=False, index=True)
    
    # Processing status
    processing_status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    processing_started = db.Column(db.DateTime, nullable=True)
    processing_completed = db.Column(db.DateTime, nullable=True)
    processing_error = db.Column(db.Text, nullable=True)
    
    # Extraction results
    extracted_queries = db.Column(db.Integer, default=0)
    extracted_qa_pairs = db.Column(db.Integer, default=0)
    extraction_confidence = db.Column(db.Float, nullable=True)
    
    # Metadata
    uploaded_by = db.Column(db.String(120), nullable=False)
    upload_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    extracted_items = db.relationship("ExtractedItem", backref="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<DocumentProcessing {self.original_filename}>'


class ExtractedItem(db.Model):
    __tablename__ = 'extracted_item'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document_processing.id', ondelete='CASCADE'), nullable=False)
    
    # Extracted content
    item_type = db.Column(db.String(20), nullable=False)  # question, answer, qa_pair, statement
    content = db.Column(db.Text, nullable=False)
    confidence_score = db.Column(db.Float, nullable=True)
    
    # Position in document
    page_number = db.Column(db.Integer, nullable=True)
    bounding_box = db.Column(db.JSON, nullable=True)  # x, y, width, height
    text_context = db.Column(db.Text, nullable=True)  # Surrounding text for context
    
    # Processing
    processed_to_query = db.Column(db.Boolean, default=False)
    audit_query_id = db.Column(db.Integer, db.ForeignKey('audit_query.id', ondelete='SET NULL'), nullable=True)
    processing_notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<ExtractedItem {self.item_type} - {self.id}>'
