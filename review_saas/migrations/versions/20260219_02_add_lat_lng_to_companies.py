# review_saas/migrations/versions/20260219_02_add_lat_lng_to_companies.py

from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = "20260219_02_add_lat_lng_to_companies"
down_revision = "20260219_01_add_owner_id_to_companies"  # <- previous migration in your snippet
branch_labels = None
depends_on = None

def upgrade():
    # Add columns only if they don't already exist (safe for re-runs)
    op.add_column("companies", sa.Column("lat", sa.Float(precision=10, asdecimal=True), nullable=True))
    op.add_column("companies", sa.Column("lng", sa.Float(precision=10, asdecimal=True), nullable=True))

def downgrade():
    op.drop_column("companies", "lng")
    op.drop_column("companies", "lat")
