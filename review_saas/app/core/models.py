# filename: review_saas/app/core/models.py
from __future__ import annotations
from datetime import datetime
from typing import List

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models with common configuration."""
    pass


# ────────────────────────────────────────────────
#               USERS & AUTHENTICATION
# ────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin, editor, viewer
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_pic: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    companies: Mapped[List["Company"]] = relationship(
        "Company", back_populates="owner", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan"
    )


# ────────────────────────────────────────────────
#               COMPANIES / LOCATIONS
# ────────────────────────────────────────────────
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    place_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )  # Google Place ID – prevents duplicates

    # Core business info from Google Places
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    hours: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string or multiline text

    # Cached / aggregated stats (updated periodically)
    avg_rating: Mapped[float | None] = mapped_column(Float, default=0.0, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    avg_sentiment: Mapped[float | None] = mapped_column(Float, default=0.0, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), default="active"
    )  # active | paused | archived

    last_review_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    google_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # full Google Places snapshot

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    owner: Mapped["User | None"] = relationship("User", back_populates="companies")
    reviews: Mapped[List["Review"]] = relationship(
        "Review", back_populates="company", cascade="all, delete-orphan"
    )


# ────────────────────────────────────────────────
#               REVIEWS & SENTIMENT ANALYSIS
# ────────────────────────────────────────────────
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", name="uq_review_company_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="google", index=True
    )  # google, trustpilot, facebook, etc.
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    rating: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Sentiment & NLP
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1.0 → +1.0
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)

    keywords: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)
    topics: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)  # e.g. ["service", "cleanliness"]

    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)  # for moderation

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")


# ────────────────────────────────────────────────
#               NOTIFICATIONS
# ────────────────────────────────────────────────
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[str] = mapped_column(String(64), nullable=False)  # info, warning, success, error
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")


# ────────────────────────────────────────────────
#               AUDIT LOGS (for compliance & debugging)
# ────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # company, review, user
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")
