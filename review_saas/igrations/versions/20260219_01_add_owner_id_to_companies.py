# review_saas/migrations/versions/20260219_01_add_owner_id_to_companies.py

from alembic import op
import sqlalchemy as sa

revision = '20260219_01_add_owner_id_to_companies'
down_revision = '20260218_03_create_companies_table'  # <- set this to your last applied migration
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('companies', sa.Column('owner_id', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('companies', 'owner_id')
