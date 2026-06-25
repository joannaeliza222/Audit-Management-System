"""merge audit query and pgvector migrations

Revision ID: 8eeb7b5261a5
Revises: 9b1c2d7a4f31, add_audit_query_models
Create Date: 2026-03-09 10:16:06.425969

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8eeb7b5261a5'
down_revision = ('9b1c2d7a4f31', 'add_audit_query_models')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
