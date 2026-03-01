# filename: app/models/models.py

from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey,
    Text, Float, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, synonym
from .base import Base


# ────────────────────────────────────────────────
# USER MODEL (UPDATED & FIXED)
# ────────────────────────────────────────────────
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)

    # Basic Info
    full_name = Column(String(100), nullable=False)
    # Provide a friendly alias so code using "user.name" still works
    name = synonym('full_name')

    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Account Status
    status = Column(String(20), default='pending', nullable=False)  # pending/active/suspended
    profile_pic_url = Column(String(255))
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # --- AUTH & SECURITY (FIXED) ---
    # This column MUST exist in your DB to avoid UndefinedColumn errors.
    # Using length 64 is standard for TOTP secrets; if your DB column is TEXT, it's also fine in Postgres.
    otp_secret = Column(String(64), nullable=True)

    oauth_google_sub = Column(String(255), unique=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    lockout_until = Column(DateTime, nullable=True)

    # Relationships
    companies = relationship('Company', back_populates='owner', cascade='all, delete-orphan')
    verification_tokens = relationship('VerificationToken', back_populates='user', cascade='all, delete-orphan')
    reset_tokens = relationship('ResetToken', back_populates='user', cascade='all, delete-orphan')
    login_attempts = relationship('LoginAttempt', back_populates='user', cascade='all, delete-orphan')
    notifications = relationship('Notification', back_populates='user', cascade='all, delete-orphan')


# ────────────────────────────────────────────────
# VERIFICATION TOKEN
# ────────────────────────────────────────────────
class VerificationToken(Base):
    __tablename__ = 'verification_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship('User', back_populates='verification_tokens')


# ────────────────────────────────────────────────
# RESET TOKEN
# ────────────────────────────────────────────────
class ResetToken(Base):
    __tablename__ = 'reset_tokens'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship('User', back_populates='reset_tokens')


# ────────────────────────────────────────────────
# LOGIN ATTEMPTS
# ────────────────────────────────────────────────
class LoginAttempt(Base):
    __tablename__ = 'login_attempts'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    success = Column(Boolean, nullable=False)
    ip_address = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship('User', back_populates='login_attempts')


# ────────────────────────────────────────────────
# COMPANY
# ────────────────────────────────────────────────
class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    name = Column(String(255), nullable=False)
    place_id = Column(String(128))
    maps_link = Column(String(512))
    city = Column(String(128))
    status = Column(String(20), default='active', nullable=False)
    logo_url = Column(String(255))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_synced_at = Column(DateTime)

    owner = relationship('User', back_populates='companies')
    reviews = relationship('Review', back_populates='company', cascade='all, delete-orphan')
    notifications = relationship('Notification', back_populates='company', cascade='all, delete-orphan')
    reports = relationship('Report', back_populates='company', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_company_owner_status', 'owner_id', 'status'),
        Index('idx_company_place_id', 'place_id'),
    )


# ────────────────────────────────────────────────
# REVIEWS
# ────────────────────────────────────────────────
class Review(Base):
    __tablename__ = 'reviews'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    external_id = Column(String(128))
    text = Column(Text)
    rating = Column(Integer)
    review_date = Column(DateTime)
    reviewer_name = Column(String(255))
    reviewer_avatar = Column(String(255))
    sentiment_category = Column(String(20))
    sentiment_score = Column(Float)
    keywords = Column(String(512))
    fetch_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    fetch_status = Column(String(20), default='Success', nullable=False)

    company = relationship('Company', back_populates='reviews')
    replies = relationship('Reply', back_populates='review', cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('company_id', 'external_id', name='uq_review_company_ext'),
        Index('idx_review_sentiment', 'sentiment_category'),
    )


# ────────────────────────────────────────────────
# REPLIES
# ────────────────────────────────────────────────
class Reply(Base):
    __tablename__ = 'replies'

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey('reviews.id', ondelete='CASCADE'), nullable=False)
    suggested_text = Column(Text)
    edited_text = Column(Text)
    status = Column(String(20), default='Draft', nullable=False)
    suggested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = Column(DateTime)

    review = relationship('Review', back_populates='replies')


# ────────────────────────────────────────────────
# REPORTS
# ────────────────────────────────────────────────
class Report(Base):
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(255))
    path = Column(String(512))
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship('Company', back_populates='reports')


# ────────────────────────────────────────────────
# NOTIFICATIONS
# ────────────────────────────────────────────────
class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    kind = Column(String(50))
    payload = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = Column(Boolean, default=False, nullable=False)

    user = relationship('User', back_populates='notifications')
    company = relationship('Company', back_populates='notifications')
