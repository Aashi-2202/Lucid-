"""Track verified signup email without altering existing credentials or jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0003_email_verification"
down_revision = "0002_additional_competencies"
branch_labels = None
depends_on = None


def upgrade():
    if "email_verified_at" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("recruiters")}:
        op.add_column("recruiters", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # upgrade_connection creates missing model tables on both new and existing DBs.
    from app.models.email_verification import EmailVerification
    EmailVerification.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Downgrade would discard verification state. Restore a reviewed backup instead.")
