
# filename: alembic/versions/0001_init.py
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = '0001_init'
 down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('full_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('profile_pic_url', sa.String(length=255)),
        sa.Column('last_login_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('otp_secret', sa.String(length=32)),
        sa.Column('oauth_google_sub', sa.String(length=255), unique=True),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table('verification_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('reset_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('login_attempts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('ip_address', sa.String(length=50)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('companies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('place_id', sa.String(length=128)),
        sa.Column('maps_link', sa.String(length=512)),
        sa.Column('city', sa.String(length=128)),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('logo_url', sa.String(length=255)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_synced_at', sa.DateTime()),
        sa.Column('lat', sa.Float()),
        sa.Column('lng', sa.Float()),
        sa.Column('email', sa.String(length=255)),
        sa.Column('phone', sa.String(length=50)),
        sa.Column('address', sa.String(length=512)),
        sa.Column('description', sa.Text()),
    )

    op.create_table('reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(length=128)),
        sa.Column('text', sa.Text()),
        sa.Column('rating', sa.Integer()),
        sa.Column('review_date', sa.DateTime()),
        sa.Column('reviewer_name', sa.String(length=255)),
        sa.Column('reviewer_avatar', sa.String(length=255)),
        sa.Column('sentiment_category', sa.String(length=20)),
        sa.Column('sentiment_score', sa.Float()),
        sa.Column('keywords', sa.String(length=512)),
        sa.Column('language', sa.String(length=10)),
        sa.Column('fetch_at', sa.DateTime(), nullable=False),
        sa.Column('fetch_status', sa.String(length=20), nullable=False, server_default='Success'),
    )
    op.create_unique_constraint('uq_review_company_ext', 'reviews', ['company_id','external_id'])

    op.create_table('replies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('reviews.id', ondelete='CASCADE'), nullable=False),
        sa.Column('suggested_text', sa.Text()),
        sa.Column('edited_text', sa.Text()),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Draft'),
        sa.Column('suggested_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime()),
    )

    op.create_table('reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=255)),
        sa.Column('path', sa.String(length=512)),
        sa.Column('meta', sa.Text()),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE')),
        sa.Column('kind', sa.String(length=50)),
        sa.Column('payload', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )

def downgrade():
    for t in ['notifications','reports','replies','reviews','companies','login_attempts','reset_tokens','verification_tokens','users']:
        op.drop_table(t)
