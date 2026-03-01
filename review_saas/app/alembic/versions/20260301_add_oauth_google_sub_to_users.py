# filename: app/alembic/versions/20260301_add_oauth_google_sub_to_users.py
"""add oauth_google_sub to users

Revision ID: 20260301_add_oauth_google_sub_to_users
Revises: <PUT_YOUR_PREVIOUS_REVISION_ID_HERE>
Create Date: 2026-03-01 14:45:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260301_add_oauth_google_sub_to_users"
down_revision = "<PUT_YOUR_PREVIOUS_REVISION_ID_HERE>"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable; size 255 is safe for Google subject ids
    op.add_column(
        "users",
        sa.Column("oauth_google_sub", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column("users", "oauth_google_sub")
