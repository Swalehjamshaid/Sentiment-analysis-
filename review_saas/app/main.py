# FILE: app/models.py
from datetime import datetime, timezone, timedelta
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
    full_name = db.Column(db.String(100), nullable=False) # Requirement 1 & 21
    email = db.Column(db.String(255), unique=True, index=True, nullable=False) # Req 2 & 22
    password_hash = db.Column(db.String(255), nullable=False) # Req 7 & 23
    
    # Account Status (active, suspended, pending)
    status = db.Column(db.String(20), default="pending", nullable=False) # Req 24
    profile_pic_url = db.Column(db.String(255), nullable=True) # Req 4 & 25
    
    # Timestamps & Security
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Req 26
    last_login_at = db.Column(DateTime, nullable=True) # Req 27
    
    # Login Attempt Management (Req 10 & 11)
    failed_login_attempts = db.Column(Integer, default=0, nullable=False)
    lockout_until = db.Column(DateTime, nullable=True)

    # Relationships
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
    token = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(DateTime, nullable=False) # Req 5 (24hr expiry)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="verification_tokens")


class ResetToken(db.Model):
    __tablename__ = "reset_tokens"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(DateTime, nullable=False) # Req 12 (30min expiry)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="reset_tokens")


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    success = db.Column(Boolean, nullable=False)
    ip_address = db.Column(db.String(50), nullable=True) # Req 9 & 31
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="login_attempts")


# =========================================================
# COMPANY MODEL
# =========================================================

class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(Integer, primary_key=True) # Req 41
    owner_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False) # Req 42

    name = db.Column(db.String(255), nullable=False) # Req 43
    place_id = db.Column(db.String(128), nullable=True, index=True) # Req 33 & 44
    maps_link = db.Column(db.String(512), nullable=True) # Req 33 & 44

    city = db.Column(db.String(128), nullable=True) # Req 45
    status = db.Column(db.String(20), default="active", nullable=False) # Req 46
    logo_url = db.Column(db.String(255), nullable=True) # Req 47
    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Req 48

    # Integration data
    last_synced_at = db.Column(DateTime, nullable=True)
    address = db.Column(db.String(512), nullable=True)

    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="company", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner_id", "place_id", name="uq_owner_company"), # Req 38
        Index("idx_company_owner_status", "owner_id", "status"),
    )


# =========================================================
# REVIEW MODEL
# =========================================================

class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(Integer, primary_key=True) # Req 58
    company_id = db.Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False) # Req 59

    external_id = db.Column(db.String(128), nullable=True) # Google Review ID
    text = db.Column(Text, nullable=True) # Req 60
    rating = db.Column(Integer, nullable=True) # Req 61

    review_date = db.Column(DateTime, nullable=True) # Req 62
    reviewer_name = db.Column(db.String(255), nullable=True) # Req 63
    reviewer_avatar = db.Column(db.String(255), nullable=True) # Req 64

    # Sentiment Analysis (Req 65, 73, 76, 79)
    sentiment_category = db.Column(db.String(20), nullable=True) # Positive/Neutral/Negative
    sentiment_score = db.Column(Float, nullable=True) # 0 to 1
    
    keywords = db.Column(db.Text, nullable=True) # Req 75 & 80
    language = db.Column(db.String(10), nullable=True) # Req 77

    fetch_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Req 66
    fetch_status = db.Column(db.String(20), default="Success", nullable=False) # Req 67

    company = relationship("Company", back_populates="reviews")
    replies = relationship("Reply", back_populates="review", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "external_id", name="uq_review_company_ext"), # Req 70
        Index("idx_review_sentiment", "sentiment_category"),
    )


# =========================================================
# SUPPORTING MODELS
# =========================================================

class Reply(db.Model):
    __tablename__ = "replies"

    id = db.Column(Integer, primary_key=True) # Req 89
    review_id = db.Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)

    suggested_text = db.Column(Text, nullable=True) # Req 90
    edited_text = db.Column(Text, nullable=True) # Req 91

    status = db.Column(db.String(20), default="Draft", nullable=False) # Req 92 (Draft/Sent)
    suggested_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False) # Req 93
    sent_at = db.Column(DateTime, nullable=True) # Req 94

    review = relationship("Review", back_populates="replies")


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(Integer, primary_key=True)
    company_id = db.Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    title = db.Column(db.String(255), nullable=True) # Req 109
    path = db.Column(db.String(512), nullable=True) # Storage path for PDF
    generated_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", back_populates="reports")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = db.Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)

    kind = db.Column(db.String(50), nullable=True) # e.g., "negative_review_alert" (Req 119)
    payload = db.Column(db.Text, nullable=True)

    created_at = db.Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = db.Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="notifications")
    company = relationship("Company", back_populates="notifications")
