"""Adopt the existing MVP schema and add optional local account credentials.

The application initializes missing tables before this upgrade. Existing Google
identity values, recruiter IDs, jobs and assessment foreign keys are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_password_accounts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns("recruiters")}
    # Fresh databases already have the current model; existing databases need
    # these additions. Batch mode also makes the legacy upgrade testable on SQLite.
    with op.batch_alter_table("recruiters") as batch:
        if "username" not in columns:
            batch.add_column(sa.Column("username", sa.String(40), nullable=True))
            batch.create_index("ix_recruiters_username", ["username"], unique=True)
        if "password_hash" not in columns:
            batch.add_column(sa.Column("password_hash", sa.String(255), nullable=True))
        for name in ("google_id", "email"):
            if not columns[name]["nullable"]:
                batch.alter_column(name, existing_type=sa.String(255), nullable=True)


def downgrade():
    raise RuntimeError("Automatic downgrade would discard local account credentials. Restore a reviewed backup instead.")
