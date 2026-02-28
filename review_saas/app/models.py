# app/models.py

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, Float, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


# =========================
# USERS
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    profile_picture = Column(String(300), nullable=True)

    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_suspended = Column(Boolean, default=False)

    failed_login_attempts = Column(Integer, default=0)
    lock_until = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    companies = relationship("Company", back_populates="owner")


# =========================
# EMAIL TOKENS (Verification + Reset)
# =========================
class EmailToken(Base):
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String(300), unique=True)
    token_type = Column(String(50))  # verify / reset
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================
# LOGIN ATTEMPTS
# =========================
class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ip_address = Column(String(100))
    success = Column(Boolean)
    timestamp = Column(DateTime, default=datetime.utcnow)


# =========================
# COMPANIES
# =========================
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    name = Column(String(200), nullable=False)
    google_place_id = Column(String(200), nullable=True)
    maps_link = Column(String(500), nullable=True)
    city = Column(String(100), nullable=True)
    logo_url = Column(String(300), nullable=True)

    status = Column(String(20), default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company")

    __table_args__ = (
        UniqueConstraint("user_id", "google_place_id", name="unique_company_per_user"),
    )


# =========================
# REVIEWS
# =========================
class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))

    review_text = Column(Text)
    rating = Column(Integer)
    review_date = Column(DateTime)

    reviewer_name = Column(String(200), nullable=True)
    reviewer_photo = Column(String(300), nullable=True)

    sentiment_category = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    keywords = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)

    fetch_date = Column(DateTime, default=datetime.utcnow)
    fetch_status = Column(String(20))  # Success / Failed / Skipped

    company = relationship("Company", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("company_id", "review_date", "reviewer_name", name="unique_review"),
    )


# =========================
# AI REPLIES
# =========================
class Reply(Base):
    __tablename__ = "replies"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id"))

    suggested_reply = Column(Text)
    user_edited_reply = Column(Text, nullable=True)

    status = Column(String(20), default="Draft")
    date_suggested = Column(DateTime, default=datetime.utcnow)
    date_sent = Column(DateTime, nullable=True)


# =========================
# ADMIN TRACKING
# =========================
class SystemStats(Base):
    __tablename__ = "system_stats"

    id = Column(Integer, primary_key=True)
    total_reviews_fetched = Column(Integer, default=0)
    total_users = Column(Integer, default=0)
    avg_rating = Column(Float, default=0.0)
    sentiment_breakdown = Column(Text, nullable=True)
