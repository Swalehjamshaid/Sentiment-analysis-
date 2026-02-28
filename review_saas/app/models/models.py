# filename: app/models/models.py
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False) # Point 1
    email = Column(String(255), unique=True, index=True, nullable=False) # Point 2
    password_hash = Column(String(255), nullable=False) # Point 7
    status = Column(String(20), default='pending', nullable=False) # Point 24 (pending/active/suspended)
    profile_pic_url = Column(String(255)) # Point 25
    last_login_at = Column(DateTime) # Point 27
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Point 26
    
    # --- Auth & Security Additions ---
    otp_secret = Column(String(32)) # Point 19 (2FA)
    oauth_google_sub = Column(String(255), unique=True) # Point 15
    failed_login_attempts = Column(Integer, default=0, nullable=False) # Point 10
    lockout_until = Column(DateTime, nullable=True) # Point 11

    # Relationships
    companies = relationship('Company', back_populates='owner', cascade='all, delete-orphan')
    verification_tokens = relationship('VerificationToken', back_populates='user', cascade='all, delete-orphan')
    reset_tokens = relationship('ResetToken', back_populates='user', cascade='all, delete-orphan')
    login_attempts = relationship('LoginAttempt', back_populates='user', cascade='all, delete-orphan')
    notifications = relationship('Notification', back_populates='user', cascade='all, delete-orphan')

class VerificationToken(Base):
    __tablename__ = 'verification_tokens'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), unique=True, nullable=False) # Point 5
    expires_at = Column(DateTime, nullable=False) # Point 5
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user = relationship('User', back_populates='verification_tokens')

class ResetToken(Base):
    __tablename__ = 'reset_tokens'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), unique=True, nullable=False) # Point 12
    expires_at = Column(DateTime, nullable=False) # Point 12 (30 min)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user = relationship('User', back_populates='reset_tokens')

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    success = Column(Boolean, nullable=False)
    ip_address = Column(String(50)) # Point 9 & 31
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Point 9
    user = relationship('User', back_populates='login_attempts')

class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True) # Point 41
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL')) # Point 42
    name = Column(String(255), nullable=False) # Point 43
    place_id = Column(String(128)) # Point 44
    maps_link = Column(String(512)) # Point 44
    city = Column(String(128)) # Point 45
    status = Column(String(20), default='active', nullable=False) # Point 46
    logo_url = Column(String(255)) # Point 47
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Point 48
    last_synced_at = Column(DateTime)
    
    owner = relationship('User', back_populates='companies')
    reviews = relationship('Review', back_populates='company', cascade='all, delete-orphan')
    notifications = relationship('Notification', back_populates='company', cascade='all, delete-orphan')
    reports = relationship('Report', back_populates='company', cascade='all, delete-orphan')

    __table_args__ = (
        Index('idx_company_owner_status', 'owner_id', 'status'),
        Index('idx_company_place_id', 'place_id'),
    )

class Review(Base):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True) # Point 58
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False) # Point 59
    external_id = Column(String(128)) # Google's unique review ID
    text = Column(Text) # Point 60 (Trimmed to 5000 in logic)
    rating = Column(Integer) # Point 61 (1-5)
    review_date = Column(DateTime) # Point 62
    reviewer_name = Column(String(255)) # Point 63
    reviewer_avatar = Column(String(255)) # Point 64
    sentiment_category = Column(String(20)) # Point 65 & 79
    sentiment_score = Column(Float) # Point 76 & 80
    keywords = Column(String(512)) # Point 75 & 80
    fetch_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Point 66
    fetch_status = Column(String(20), default='Success', nullable=False) # Point 67

    company = relationship('Company', back_populates='reviews')
    replies = relationship('Reply', back_populates='review', cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('company_id', 'external_id', name='uq_review_company_ext'), # Point 70
        Index('idx_review_sentiment', 'sentiment_category'),
    )

class Reply(Base):
    __tablename__ = 'replies'
    id = Column(Integer, primary_key=True) # Point 89
    review_id = Column(Integer, ForeignKey('reviews.id', ondelete='CASCADE'), nullable=False)
    suggested_text = Column(Text) # Point 90
    edited_text = Column(Text) # Point 91
    status = Column(String(20), default='Draft', nullable=False) # Point 92 (Draft/Sent)
    suggested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Point 93
    sent_at = Column(DateTime) # Point 94
    review = relationship('Review', back_populates='replies')

class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(255)) # Point 109
    path = Column(String(512)) # Path to generated PDF
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    company = relationship('Company', back_populates='reports')

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'))
    kind = Column(String(50)) # Point 119 (negative_review, drop_in_rating)
    payload = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = Column(Boolean, default=False, nullable=False)
    user = relationship('User', back_populates='notifications')
    company = relationship('Company', back_populates='notifications')
