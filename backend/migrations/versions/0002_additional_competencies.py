"""Add optional reporting-only job competencies; preserve existing job/results."""
from alembic import op
import sqlalchemy as sa

revision = "0002_additional_competencies"
down_revision = "0001_password_accounts"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("jobs")}
    if "additional_competencies" not in columns:
        op.add_column("jobs", sa.Column("additional_competencies", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    raise RuntimeError("Downgrade would discard saved competencies. Restore a reviewed backup instead.")
