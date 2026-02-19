# File: review_saas/migrations/versions/20260219_01_add_owner_id_to_companies.py

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260219_01_add_owner_id_to_companies'

# <-- Set this to your last applied migration’s revision ID
down_revision = '20260218_03_create_companies_table'  # replace with your actual last migration ID
branch_labels = None
depends_on = None

def upgrade():
    """Add owner_id column to companies table"""
    op.add_column(
        'companies',
        sa.Column('owner_id', sa.Integer(), nullable=True)
    )

def downgrade():
    """Remove owner_id column from companies table"""
    op.drop_column('companies', 'owner_id')
