"""Document Q&A system migration

Revision ID: document_qa_001
Revises: 
Create Date: 2024-04-28 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'document_qa_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create secure_documents table
    op.create_table(
        'secure_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.Enum('uploading', 'processing', 'ready', 'failed', 'deleted', name='documentstatus'), nullable=False),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('processing_started_at', sa.DateTime(), nullable=True),
        sa.Column('processing_completed_at', sa.DateTime(), nullable=True),
        sa.Column('access_level', sa.Enum('private', 'shared', name='documentaccesslevel'), nullable=False),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False),
        sa.Column('encryption_key_hash', sa.String(length=64), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('extracted_text_length', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stored_filename')
    )
    
    # Create indexes for secure_documents
    op.create_index('idx_document_user_status', 'secure_documents', ['user_id', 'status'])
    op.create_index('idx_document_created_at', 'secure_documents', ['created_at'])
    op.create_index('idx_document_file_hash', 'secure_documents', ['file_hash'])
    
    # Create qa_document_chunks table
    op.create_table(
        'qa_document_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column('chunk_type', sa.String(length=50), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['secure_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for qa_document_chunks
    op.create_index('idx_qa_chunk_document_user', 'qa_document_chunks', ['document_id', 'user_id'])
    op.create_index('idx_qa_chunk_index', 'qa_document_chunks', ['document_id', 'chunk_index'])
    
    # Create qa_sessions table
    op.create_table(
        'qa_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_name', sa.String(length=255), nullable=True),
        sa.Column('session_token', sa.String(length=64), nullable=False),
        sa.Column('question_count', sa.Integer(), nullable=False),
        sa.Column('last_activity_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['secure_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_token')
    )
    
    # Create indexes for qa_sessions
    op.create_index('idx_session_document_user', 'qa_sessions', ['document_id', 'user_id'])
    op.create_index('idx_session_token', 'qa_sessions', ['session_token'])
    op.create_index('idx_session_last_activity', 'qa_sessions', ['last_activity_at'])
    
    # Create qa_conversations table
    op.create_table(
        'qa_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('question_embedding', postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('answer_sources', sa.Text(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('relevant_chunks', sa.Text(), nullable=True),
        sa.Column('context_length', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['qa_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for qa_conversations
    op.create_index('idx_conversation_session_user', 'qa_conversations', ['session_id', 'user_id'])
    op.create_index('idx_conversation_created_at', 'qa_conversations', ['created_at'])
    
    # Create document_access_logs table
    op.create_table(
        'document_access_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('session_id', sa.String(length=64), nullable=True),
        sa.Column('additional_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['secure_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for document_access_logs
    op.create_index('idx_access_document_user', 'document_access_logs', ['document_id', 'user_id'])
    op.create_index('idx_access_action', 'document_access_logs', ['action'])
    op.create_index('idx_access_created_at', 'document_access_logs', ['created_at'])
    
    # Create document_shares table
    op.create_table(
        'document_shares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('shared_by_user_id', sa.Integer(), nullable=False),
        sa.Column('shared_with_user_id', sa.Integer(), nullable=True),
        sa.Column('share_token', sa.String(length=64), nullable=False),
        sa.Column('permission_level', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('max_queries', sa.Integer(), nullable=True),
        sa.Column('query_count', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['secure_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_by_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_with_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('share_token')
    )
    
    # Create indexes for document_shares
    op.create_index('idx_share_document_shared_by', 'document_shares', ['document_id', 'shared_by_user_id'])
    op.create_index('idx_share_token', 'document_shares', ['share_token'])
    op.create_index('idx_share_active', 'document_shares', ['is_active', 'expires_at'])


def downgrade():
    # Drop tables in reverse order of creation
    op.drop_table('document_shares')
    op.drop_table('document_access_logs')
    op.drop_table('qa_conversations')
    op.drop_table('qa_sessions')
    op.drop_table('qa_document_chunks')
    op.drop_table('secure_documents')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS documentstatus')
    op.execute('DROP TYPE IF EXISTS documentaccesslevel')
