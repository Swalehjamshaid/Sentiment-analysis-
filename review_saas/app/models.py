# filename: app/models.py
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint, Index
from .db import db

# =============== Users & Auth ===============
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending/active/suspended
    profile_pic_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = db.Column(db.DateTime)

    companies = db.relationship('Company', back_populates='owner', cascade='all, delete-orphan')
    verification_tokens = db.relationship('VerificationToken', back_populates='user', cascade='all, delete-orphan')
    reset_tokens = db.relationship('ResetToken', back_populates='user', cascade='all, delete-orphan')
    login_attempts = db.relationship('LoginAttempt', back_populates='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan')

class VerificationToken(db.Model):
    __tablename__ = 'verification_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user = db.relationship('User', back_populates='verification_tokens')

class ResetToken(db.Model):
    __tablename__ = 'reset_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user = db.relationship('User', back_populates='reset_tokens')

class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    success = db.Column(db.Boolean, nullable=False)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user = db.relationship('User', back_populates='login_attempts')

# =============== Company ===============
class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    name = db.Column(db.String(255), nullable=False)
    place_id = db.Column(db.String(128))
    maps_link = db.Column(db.String(512))
    city = db.Column(db.String(128))
    status = db.Column(db.String(20), default='active', nullable=False)
    logo_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_synced_at = db.Column(db.DateTime)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    address = db.Column(db.String(512))
    description = db.Column(db.Text)

    owner = db.relationship('User', back_populates='companies')
    reviews = db.relationship('Review', back_populates='company', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', back_populates='company', cascade='all, delete-orphan')
    reports = db.relationship('Report', back_populates='company', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_company_owner_status', 'owner_id', 'status'),
        Index('idx_company_place_id', 'place_id'),
        Index('idx_company_created', 'created_at'),
        UniqueConstraint('owner_id', 'name', name='uq_owner_company'),
    )

# =============== Reviews ===============
class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    external_id = db.Column(db.String(128))
    text = db.Column(db.Text)
    rating = db.Column(db.Integer)
    review_date = db.Column(db.DateTime)
    reviewer_name = db.Column(db.String(255))
    reviewer_avatar = db.Column(db.String(255))
    sentiment_category = db.Column(db.String(20))
    sentiment_score = db.Column(db.Float)
    keywords = db.Column(db.String(512))
    language = db.Column(db.String(10))
    fetch_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    fetch_status = db.Column(db.String(20), default='Success', nullable=False)

    company = db.relationship('Company', back_populates='reviews')
    replies = db.relationship('Reply', back_populates='review', cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('company_id', 'external_id', name='uq_review_company_ext'),
        Index('idx_review_company_date', 'company_id', 'review_date'),
        Index('idx_review_rating', 'rating'),
        Index('idx_review_sentiment', 'sentiment_category'),
    )

# =============== Replies / Reports / Notifications ===============
class Reply(db.Model):
    __tablename__ = 'replies'
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id', ondelete='CASCADE'), nullable=False)
    suggested_text = db.Column(db.Text)
    edited_text = db.Column(db.Text)
    status = db.Column(db.String(20), default='Draft', nullable=False)
    suggested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = db.Column(db.DateTime)
    review = db.relationship('Review', back_populates='replies')

class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255))
    path = db.Column(db.String(512))
    meta = db.Column(db.Text)
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    company = db.relationship('Company', back_populates='reports')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'))
    kind = db.Column(db.String(50))
    payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship('User', back_populates='notifications')
    company = db.relationship('Company', back_populates='notifications')
