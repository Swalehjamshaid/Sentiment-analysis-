# FILE: app/models.py

from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Float,
    UniqueConstraint,
    Index,
)
from datetime import datetime, timezone

Base = declarative_base()

# =========================================================
# USER MODEL
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    profile_pic_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    verification_tokens = relationship("VerificationToken", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("ResetToken", back_populates="user", cascade="all, delete-orphan")
    login_attempts = relationship("LoginAttempt", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


# =========================================================
# TOKEN & LOG MODELS
# =========================================================

class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="verification_tokens")


class ResetToken(Base):
    __tablename__ = "reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="reset_tokens")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    success = Column(Boolean, nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="login_attempts")


# =========================================================
# COMPANY MODEL
# =========================================================

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    place_id = Column(String(128), nullable=True)
    maps_link = Column(String(512), nullable=True)

    city = Column(String(128), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    logo_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # CRITICAL: Field to track last sync with Google API
    last_synced_at = Column(DateTime, nullable=True)

    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)

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

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    external_id = Column(String(128), nullable=True)
    text = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)

    # CRITICAL: Must be DateTime to support hour extraction in analytics
    review_date = Column(DateTime, nullable=True)
    reviewer_name = Column(String(255), nullable=True)
    reviewer_avatar = Column(String(255), nullable=True)

    sentiment_category = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)

    keywords = Column(String(512), nullable=True)
    language = Column(String(10), nullable=True)

    fetch_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    fetch_status = Column(String(20), default="Success", nullable=False)

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

class Reply(Base):
    __tablename__ = "replies"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)

    suggested_text = Column(Text, nullable=True)
    edited_text = Column(Text, nullable=True)

    status = Column(String(20), default="Draft", nullable=False)
    suggested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = Column(DateTime, nullable=True)

    review = relationship("Review", back_populates="replies")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(255), nullable=True)
    path = Column(String(512), nullable=True)
    meta = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", back_populates="reports")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)

    kind = Column(String(50), nullable=True)
    payload = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="notifications")
    company = relationship("Company", back_populates="notifications")
