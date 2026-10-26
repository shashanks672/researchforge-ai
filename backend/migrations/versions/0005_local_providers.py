"""allow local model execution mode"""

import sqlalchemy as sa
from alembic import op

revision = "0005_local_providers"
down_revision = "0004_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_run_mode", "research_runs", type_="check")
    op.create_check_constraint(
        "ck_run_mode", "research_runs", "execution_mode IN ('mock', 'local', 'live')"
    )


def downgrade() -> None:
    connection = op.get_bind()
    local_runs = connection.scalar(
        sa.text("SELECT count(*) FROM research_runs WHERE execution_mode = 'local'")
    )
    if local_runs:
        raise RuntimeError("Cannot downgrade while local-model research runs are stored")
    op.drop_constraint("ck_run_mode", "research_runs", type_="check")
    op.create_check_constraint("ck_run_mode", "research_runs", "execution_mode IN ('mock', 'live')")
