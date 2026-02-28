# FILE: app/models.py
# NOTE: Flask‑SQLAlchemy models (db.Model), not declarative_base()

from datetime import datetime, timezone
from sqlalchemy import (
    Integer, String, DateTime, Boolean, ForeignKey, Text, Float,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .db import db

# =========================================================
# USER MODEL
# =========================================================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(Integer, primary_key=True)
    full_name = db.Column(String(100), nullable=False)
    email = db.Column(String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(String(255), nullable=False)
    status = db.Column(String(20), default="pending", nullable=False)
    profile_pic_url = db.Column(String(255), nullable=True)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    verification_tokens = relationship("VerificationToken", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("ResetToken", back_populates="user", cascade="all, delete-orphan")
    login_attempts = relationship("LoginAttempt", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


# =========================================================
# TOKEN & LOG MODELS
# =========================================================

class VerificationToken(db.Model):
    __tablename__ = "verification_tokens"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(String(255), nullable=False, unique=True)
    expires_at = db.Column(DateTime, nullable=False)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="verification_tokens")


class ResetToken(db.Model):
    __tablename__ = "reset_tokens"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(String(255), nullable=False, unique=True)
    expires_at = db.Column(DateTime, nullable=False)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="reset_tokens")


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    success = db.Column(Boolean, nullable=False)
    ip_address = db.Column(String(50), nullable=True)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="login_attempts")


# =========================================================
# COMPANY MODEL
# =========================================================

class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(Integer, primary_key=True)
    owner_id = db.Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = db.Column(String(255), nullable=False)
    place_id = db.Column(String(128), nullable=True)
    maps_link = db.Column(String(512), nullable=True)

    city = db.Column(String(128), nullable=True)
    status = db.Column(String(20), default="active", nullable=False)
    logo_url = db.Column(String(255), nullable=True)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Track last sync with Google API
    last_synced_at = db.Column(DateTime, nullable=True)

    lat = db.Column(Float, nullable=True)
    lng = db.Column(Float, nullable=True)

    email = db.Column(String(255), nullable=True)
    phone = db.Column(String(50), nullable=True)
    address = db.Column(String(512), nullable=True)
    description = db.Column(Text, nullable=True)

    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="company", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_company_owner_status", "owner_id", "status"),
        Index("idx_company_place_id", "place_id"),
        Index("idx_company_created", "created_at"),
    )


# =========================================================
# REVIEW MODEL
# =========================================================

class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(Integer, primary_key=True)
    company_id = db.Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    external_id = db.Column(String(128), nullable=True)
    text = db.Column(Text, nullable=True)
    rating = db.Column(Integer, nullable=True)

    # Must be DateTime (analytics)
    review_date = db.Column(DateTime, nullable=True)
    reviewer_name = db.Column(String(255), nullable=True)
    reviewer_avatar = db.Column(String(255), nullable=True)

    sentiment_category = db.Column(String(20), nullable=True)
    sentiment_score = db.Column(Float, nullable=True)

    keywords = db.Column(String(512), nullable=True)
    language = db.Column(String(10), nullable=True)

    fetch_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    fetch_status = db.Column(String(20), default="Success", nullable=False)

    company = relationship("Company", back_populates="reviews")
    replies = relationship("Reply", back_populates="review", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "external_id", name="uq_review_company_ext"),
        Index("idx_review_company_date", "company_id", "review_date"),
        Index("idx_review_rating", "rating"),
        Index("idx_review_sentiment", "sentiment_category"),
    )


# =========================================================
# SUPPORTING MODELS
# =========================================================

class Reply(db.Model):
    __tablename__ = "replies"

    id = db.Column(Integer, primary_key=True)
    review_id = db.Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)

    suggested_text = db.Column(Text, nullable=True)
    edited_text = db.Column(Text, nullable=True)

    status = db.Column(String(20), default="Draft", nullable=False)
    suggested_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = db.Column(DateTime, nullable=True)

    review = relationship("Review", back_populates="replies")


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(Integer, primary_key=True)
    company_id = db.Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    title = db.Column(String(255), nullable=True)
    path = db.Column(String(512), nullable=True)
    meta = db.Column(Text, nullable=True)
    generated_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", back_populates="reports")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = db.Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)

    kind = db.Column(String(50), nullable=True)
    payload = db.Column(Text, nullable=True)

    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = db.Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="notifications")
    company = relationship("Company", back_populates="notifications")
