"""Add research sessions without touching unrelated tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001_sessions"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("char_length(question) BETWEEN 10 AND 4000", name="ck_session_question"),
        sa.CheckConstraint("mode IN ('web', 'documents', 'combined')", name="ck_session_mode"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_session_status",
        ),
    )
    op.create_index(
        "ix_session_workspace_history", "research_sessions", ["workspace_id", "created_at", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_workspace_history", table_name="research_sessions")
    op.drop_table("research_sessions")
