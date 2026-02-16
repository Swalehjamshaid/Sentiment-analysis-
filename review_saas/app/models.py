
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(20), default='active')  # active/suspended
    profile_pic_url = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)
    email_verified = Column(Boolean, default=False)
    email_verification_token = Column(String(128))
    email_verification_expires = Column(DateTime)

    login_attempts = Column(Integer, default=0)
    lock_until = Column(DateTime)

    twofa_enabled = Column(Boolean, default=False)
    twofa_secret = Column(String(64))

    oauth_provider = Column(String(50))
    oauth_sub = Column(String(255))

    companies = relationship('Company', back_populates='owner')

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    ip_address = Column(String(64))
    timestamp = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=False)

class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True)
    owner_user_id = Column(Integer, ForeignKey('users.id'), index=True)
    name = Column(String(255))
    place_id = Column(String(128), index=True)
    maps_url = Column(String(512))
    city = Column(String(255))
    status = Column(String(20), default='Active')
    logo_url = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship('User', back_populates='companies')
    reviews = relationship('Review', back_populates='company')

    __table_args__ = (
        UniqueConstraint('owner_user_id', 'place_id', name='uq_owner_place'),
        UniqueConstraint('owner_user_id', 'name', name='uq_owner_name')
    )

class Review(Base):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), index=True)
    source = Column(String(50), default='google')
    external_id = Column(String(128))  # for duplicate prevention

    text = Column(Text)
    rating = Column(Integer)
    review_datetime = Column(DateTime)
    reviewer_name = Column(String(255))
    reviewer_pic_url = Column(String(512))

    sentiment_category = Column(String(20))
    sentiment_score = Column(Float)
    keywords = Column(Text)  # JSON string

    fetched_at = Column(DateTime, default=datetime.utcnow)
    fetch_status = Column(String(20), default='Success')  # Success/Failed/Skipped

    company = relationship('Company', back_populates='reviews')

    __table_args__ = (
        UniqueConstraint('company_id', 'source', 'external_id', name='uq_review_unique'),
    )

class SuggestedReply(Base):
    __tablename__ = 'suggested_replies'
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey('reviews.id'), unique=True)
    suggested_text = Column(String(500))
    user_edited_text = Column(String(500))
    status = Column(String(20), default='Draft')  # Draft/Sent
    suggested_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime)

class FetchJob(Base):
    __tablename__ = 'fetch_jobs'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    schedule = Column(String(20), default='daily')  # daily/weekly
    last_run = Column(DateTime)
    status = Column(String(20), default='Idle')

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    type = Column(String(50))  # negative_review, rating_drop
    payload = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)
