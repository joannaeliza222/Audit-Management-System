"""pgvector extension + vector indexes

Revision ID: 9b1c2d7a4f31
Revises: 3ed58e492ae4
Create Date: 2026-01-21
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "9b1c2d7a4f31"
down_revision = "3ed58e492ae4"
branch_labels = None
depends_on = None


def upgrade():
    # Ensure pgvector is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Best-effort: ensure embedding columns are vector(384) (handles legacy bytea/text)
    op.execute(
        """
        DO $$
        DECLARE
          t text;
        BEGIN
          SELECT a.atttypid::regtype::text
            INTO t
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
           WHERE n.nspname = current_schema()
             AND c.relname = 'faq'
             AND a.attname = 'embedding'
             AND a.attnum > 0
             AND NOT a.attisdropped;

          IF t IS NOT NULL AND t <> 'vector' THEN
            -- If existing values are incompatible, this will fail loudly (preferred over silent corruption).
            EXECUTE 'ALTER TABLE faq ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)';
          END IF;
        END$$;
        """
    )

    op.execute(
        """
        DO $$
        DECLARE
          t text;
        BEGIN
          SELECT a.atttypid::regtype::text
            INTO t
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
           WHERE n.nspname = current_schema()
             AND c.relname = 'draftfaq'
             AND a.attname = 'embedding'
             AND a.attnum > 0
             AND NOT a.attisdropped;

          IF t IS NOT NULL AND t <> 'vector' THEN
            EXECUTE 'ALTER TABLE draftfaq ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)';
          END IF;
        END$$;
        """
    )

    # Create ANN indexes for fast cosine similarity search (pgvector >= 0.5 typically supports HNSW)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_faq_embedding_hnsw ON faq USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_draftfaq_embedding_hnsw ON draftfaq USING hnsw (embedding vector_cosine_ops);"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_draftfaq_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS ix_faq_embedding_hnsw;")
    # Keep extension; removing it may break other objects/environments.

