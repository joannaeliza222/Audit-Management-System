"""Add audit query management models

Revision ID: add_audit_query_models
Revises: 139b789a6f88
Create Date: 2026-03-06 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_audit_query_models'
down_revision = '139b789a6f88'
branch_labels = None
depends_on = None


def upgrade():
    # Create audit_query_status enum
    op.execute("CREATE TYPE auditquerystatus AS ENUM ('received', 'in_progress', 'awaiting_response', 'responded', 'closed', 'escalated')")
    
    # Create commitment_status enum
    op.execute("CREATE TYPE commitmentstatus AS ENUM ('pending', 'in_progress', 'completed', 'overdue', 'cancelled')")
    
    # Create audit_query table
    op.create_table('audit_query',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('query_id', sa.String(length=50), nullable=False),
        sa.Column('state_name', sa.String(length=100), nullable=False),
        sa.Column('date_received', sa.Date(), nullable=False),
        sa.Column('query_description', sa.Text(), nullable=False),
        sa.Column('assigned_official', sa.String(length=200), nullable=True),
        sa.Column('assigned_official_email', sa.String(length=120), nullable=True),
        sa.Column('department', sa.String(length=200), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=True),
        sa.Column('status', sa.Enum('received', 'in_progress', 'awaiting_response', 'responded', 'closed', 'escalated', name='auditquerystatus'), nullable=False),
        sa.Column('response_provided', sa.Text(), nullable=True),
        sa.Column('response_date', sa.Date(), nullable=True),
        sa.Column('response_method', sa.String(length=50), nullable=True),
        sa.Column('source_document', sa.String(length=500), nullable=True),
        sa.Column('memo_id', sa.String(length=128), nullable=True),
        sa.Column('audit_year', sa.Integer(), nullable=True),
        sa.Column('audit_type', sa.String(length=100), nullable=True),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['faq.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('query_id')
    )
    op.create_index(op.f('ix_audit_query_audit_year'), 'audit_query', ['audit_year'], unique=False)
    op.create_index(op.f('ix_audit_query_date_received'), 'audit_query', ['date_received'], unique=False)
    op.create_index(op.f('ix_audit_query_memo_id'), 'audit_query', ['memo_id'], unique=False)
    op.create_index(op.f('ix_audit_query_state_name'), 'audit_query', ['state_name'], unique=False)
    op.create_index(op.f('ix_audit_query_status'), 'audit_query', ['status'], unique=False)
    
    # Create commitment table
    op.create_table('commitment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_query_id', sa.Integer(), nullable=False),
        sa.Column('commitment_text', sa.Text(), nullable=False),
        sa.Column('commitment_type', sa.String(length=50), nullable=True),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'in_progress', 'completed', 'overdue', 'cancelled', name='commitmentstatus'), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('overdue_notified', sa.Boolean(), nullable=True),
        sa.Column('responsible_party', sa.String(length=200), nullable=True),
        sa.Column('implementation_notes', sa.Text(), nullable=True),
        sa.Column('verification_method', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['audit_query_id'], ['audit_query.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_commitment_status'), 'commitment', ['status'], unique=False)
    op.create_index(op.f('ix_commitment_target_date'), 'commitment', ['target_date'], unique=False)
    
    # Create query_version table
    op.create_table('query_version',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_query_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('previous_status', sa.Enum('received', 'in_progress', 'awaiting_response', 'responded', 'closed', 'escalated', name='auditquerystatus'), nullable=True),
        sa.Column('new_status', sa.Enum('received', 'in_progress', 'awaiting_response', 'responded', 'closed', 'escalated', name='auditquerystatus'), nullable=True),
        sa.Column('previous_response', sa.Text(), nullable=True),
        sa.Column('new_response', sa.Text(), nullable=True),
        sa.Column('previous_assigned', sa.String(length=200), nullable=True),
        sa.Column('new_assigned', sa.String(length=200), nullable=True),
        sa.Column('changed_by', sa.String(length=120), nullable=False),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('change_timestamp', sa.DateTime(), nullable=True),
        sa.Column('full_snapshot', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['audit_query_id'], ['audit_query.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_query_version_change_timestamp'), 'query_version', ['change_timestamp'], unique=False)
    
    # Create document_processing table
    op.create_table('document_processing',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('stored_filename', sa.String(length=500), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_type', sa.String(length=10), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('processing_status', sa.String(length=50), nullable=True),
        sa.Column('processing_started', sa.DateTime(), nullable=True),
        sa.Column('processing_completed', sa.DateTime(), nullable=True),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('extracted_queries', sa.Integer(), nullable=True),
        sa.Column('extracted_qa_pairs', sa.Integer(), nullable=True),
        sa.Column('extraction_confidence', sa.Float(), nullable=True),
        sa.Column('uploaded_by', sa.String(length=120), nullable=False),
        sa.Column('upload_timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_processing_checksum'), 'document_processing', ['checksum'], unique=False)
    op.create_index(op.f('ix_document_processing_processing_status'), 'document_processing', ['processing_status'], unique=False)
    
    # Create extracted_item table
    op.create_table('extracted_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('bounding_box', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('text_context', sa.Text(), nullable=True),
        sa.Column('processed_to_query', sa.Boolean(), nullable=True),
        sa.Column('audit_query_id', sa.Integer(), nullable=True),
        sa.Column('processing_notes', sa.Text(), nullable=True),
        sa.Column('extracted_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['audit_query_id'], ['audit_query.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['document_processing.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop tables in reverse order
    op.drop_table('extracted_item')
    op.drop_table('document_processing')
    op.drop_table('query_version')
    op.drop_table('commitment')
    op.drop_table('audit_query')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS commitmentstatus")
    op.execute("DROP TYPE IF EXISTS auditquerystatus")
