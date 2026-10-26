"""Persist bounded research runs; preserve all existing sessions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_research_runs"
down_revision = "0001_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(36), nullable=False),
        sa.Column("execution_mode", sa.String(8), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False, server_default="accepted"),
        sa.Column("plan", postgresql.JSONB(), nullable=True),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("investigated_queries", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=True),
        sa.Column("report_markdown", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("provider_model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
        sa.ForeignKeyConstraint(["session_id"], ["research_sessions.id"], ondelete="CASCADE"),
        sa.CheckConstraint("execution_mode IN ('mock', 'live')", name="ck_run_mode"),
    )


def downgrade() -> None:
    op.drop_table("research_runs")
