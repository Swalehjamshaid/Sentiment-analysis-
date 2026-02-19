# File: review_saas/migrations/versions/20260219_01_add_owner_id_to_companies.py

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260219_01_add_owner_id_to_companies'
down_revision = '20260218_03_last_migration'  # <- set this to your last applied migration
branch_labels = None
depends_on = None

def upgrade():
    # Add the owner_id column to companies table
    op.add_column('companies', sa.Column('owner_id', sa.Integer(), nullable=True))

def downgrade():
    # Remove the owner_id column if you roll back
    op.drop_column('companies', 'owner_id')
