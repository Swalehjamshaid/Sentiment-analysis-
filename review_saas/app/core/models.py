# filename: app/core/models.py
from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, Float, ForeignKey, Boolean, JSON, UniqueConstraint, func, Text, ARRAY
from datetime import datetime

# -------------------- BASE --------------------
class Base(DeclarativeBase):
    pass

# -------------------- USERS --------------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_pic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    companies: Mapped[list["Company"]] = relationship(
        "Company", back_populates="owner", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan"
    )

# -------------------- COMPANIES --------------------
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    google_place_id: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    formatted_address: Mapped[str | None] = mapped_column(String(512), nullable=True)  # Preferred over raw address
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)            # Kept for compatibility
    international_phone_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)               # Kept
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    types: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)     # e.g. ["night_club", "bar"]
    hours: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(64), nullable=True)     # OPERATIONAL, CLOSED_TEMPORARILY, etc.
    price_level: Mapped[int | None] = mapped_column(Integer, nullable=True)            # 0–4
    utc_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    google_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    google_user_ratings_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    google_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Full raw response

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship("User", back_populates="companies")
    reviews: Mapped[list["Review"]] = relationship(
        "Review", back_populates="company", cascade="all, delete-orphan"
    )

# -------------------- REVIEWS --------------------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "google_review_id", name="uq_review_company_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    google_review_id: Mapped[str] = mapped_column(String(255), index=True)  # Google's review identifier (was review_id)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reviewer_is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)  # When name is "A Google user"
    rating: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_review_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    original_language: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Sometimes different
    relative_time_description: Mapped[str | None] = mapped_column(String(100), nullable=True)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # If different from time
    review_reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)       # Owner reply
    review_reply_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship("Company", back_populates="reviews")

# -------------------- NOTIFICATIONS --------------------
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(1000))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="notifications")

# -------------------- AUDIT LOGS --------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="audit_logs")
