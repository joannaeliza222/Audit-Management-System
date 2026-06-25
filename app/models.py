import enum
import uuid
from datetime import datetime
from flask import url_for
from pgvector.sqlalchemy import Vector
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash
from . import db
import hashlib
import hmac
from cryptography.fernet import Fernet


class DraftStatus(enum.Enum):
    pending = 'pending'
    admin_draft = 'admin_draft'
    merged = 'merged'
    rejected = 'rejected'


class DataDumpStatus(enum.Enum):
    requested = 'requested'
    provided = 'provided'
    rejected = 'rejected'
    acknowledged = 'acknowledged'


class Logs(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user_email = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=True)  # admin, reviewer, modifier, viewer
    state_name = db.Column(db.String(100))
    is_approved = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(100), nullable=True, index=True)
    password_reset_token = db.Column(db.String(100), nullable=True, index=True)
    password_reset_expires = db.Column(db.DateTime, nullable=True)

    def check_password(self, raw):
        return check_password_hash(self.password, raw)
    
    @property
    def is_active(self):
        """Flask-Login requirement - user is active if approved"""
        return self.is_approved
    
    @property
    def is_authenticated(self):
        """Flask-Login requirement"""
        return True
    
    @property
    def is_anonymous(self):
        """Flask-Login requirement"""
        return False
    
    def get_id(self):
        """Flask-Login requirement"""
        return str(self.id)


class FAQ(db.Model):
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
    __table_args__ = (UniqueConstraint('norm_query', 'state_name', name='uq_query_state'),)


class DraftFAQ(db.Model):
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
    __table_args__ = (UniqueConstraint('norm_query', 'state_name', name='uq_draft_query_state'),)

    future_issues = db.relationship(
        "FutureIssueTracker",
        backref="draft",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin="DraftFAQ.id == FutureIssueTracker.related_draft_id"
    )


class FutureIssueTracker(db.Model):
    __tablename__ = 'future_issue_tracker'
    id = db.Column(db.Integer, primary_key=True)
    related_draft_id = db.Column(db.Integer, db.ForeignKey('draftfaq.id', ondelete='CASCADE'), nullable=True)
    related_faq_id = db.Column(db.Integer, db.ForeignKey('faq.id', ondelete='SET NULL'), nullable=True)
    description = db.Column(db.Text, nullable=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='not addressed')
    version_detected = db.Column(db.String(50), nullable=True)
    version_fixed = db.Column(db.String(50), nullable=True)
    note = db.Column(db.Text, nullable=True)


class DataDump(db.Model):
    __tablename__ = 'data_dump'

    id = db.Column(db.Integer, primary_key=True, comment="Primary key")
    state = db.Column(db.String(100), nullable=False, comment="State name requested datadump")
    nodal_dept = db.Column(db.String(200), comment="Name of the nodal department/state")
    request_date = db.Column(db.Date, comment="Timestamp when the datadump request was mailed")
    coordinator = db.Column(db.String(200), comment="State coordinator's email id")
    request_email = db.Column(db.Text, comment="Description of data needed")

    file_name = db.Column(db.String(200), comment="Name of the file shared")
    md5_hash = db.Column(db.String(200), comment="MD5 Hash of the file shared")
    file_size = db.Column(db.String(50), comment="Size of the file")
    period_shared = db.Column(db.String(50), comment="Period upto which the data was shared")
    postgres_version = db.Column(db.String(100), comment="Postgres version in which the DB backup was taken")
    command_to_restore = db.Column(db.Text, comment="Command to retrieve the data in a new DB")
    db_size = db.Column(db.String(50), comment="Probable size of the DB after import")

    share_date = db.Column(db.Date, comment="Timestamp when the datadump was shared")
    share_mode = db.Column(db.String(200), comment="Mode through which the data is shared")
    coordinator_name = db.Column(db.String(200), comment="Name of State NIC Coordinator")
    share_link = db.Column(db.String(500))
    shared_to = db.Column(db.String(200))

    file_path = db.Column(db.String(1000))
    is_file_available = db.Column(db.Boolean, default=False)
    download_token = db.Column(db.String(100), unique=True, index=True)

    status = db.Column(db.String(20), default="requested")
    remarks = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    generated_doc = db.Column(db.String(200))
    user_uploaded_doc = db.Column(db.String(200))
    user_doc_signed = db.Column(db.Boolean, default=False)
    user_doc_verified = db.Column(db.Boolean, default=False)
    user_doc_downloaded = db.Column(db.Boolean, default=False)

    def generate_download_token(self):
        self.download_token = uuid.uuid4().hex
        return self.download_token

    def file_url(self):
        if self.is_file_available and self.file_path:
            return url_for('download_datadump', token=self.download_token)
        return None


class FailedLoginAttempt(db.Model):
    __tablename__ = 'failed_login_attempts'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), index=True, nullable=False)
    ip_address = db.Column(db.String(45))
    attempt_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    success = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<FailedLoginAttempt {self.email} {self.attempt_time}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='info')  # info, warning, success, error
    related_draft_id = db.Column(db.Integer, db.ForeignKey('draftfaq.id', ondelete='SET NULL'), nullable=True)
    related_faq_id = db.Column(db.Integer, db.ForeignKey('faq.id', ondelete='SET NULL'), nullable=True)
    related_issue_id = db.Column(db.Integer, db.ForeignKey('future_issue_tracker.id', ondelete='SET NULL'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Notification {self.title} for {self.user_email}>'
