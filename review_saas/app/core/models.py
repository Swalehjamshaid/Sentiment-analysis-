from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy.sql import func

# ---------------------------------------------------
# Base
# ---------------------------------------------------
Base = declarative_base()

# Bumped version to ensure Railway triggers a schema rebuild
SCHEMA_VERSION = "15.0.4-full-outscraper-persistence-ready"

# ---------------------------------------------------
# Users
# ---------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_pic: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="editor")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    companies = relationship("Company", back_populates="owner")

# ---------------------------------------------------
# Companies
# ---------------------------------------------------
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Google Identifiers
    google_place_id: Mapped[str | None] = mapped_column(String(512), unique=True, index=True)
    internal_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Location Details
    full_address: Mapped[str | None] = mapped_column(String(1000))
    city: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)

    # Contact
    phone: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(255))

    # Categories & Stats
    category: Mapped[str | None] = mapped_column(String(255))
    sub_categories: Mapped[list | None] = mapped_column(JSON)
    type: Mapped[list | None] = mapped_column(JSON)
    business_status: Mapped[str | None] = mapped_column(String(50))
    permanently_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)

    # Media & Hours
    photos: Mapped[list | None] = mapped_column(JSON)
    working_hours: Mapped[dict | None] = mapped_column(JSON)
    popular_times: Mapped[dict | None] = mapped_column(JSON)
    business_attributes: Mapped[dict | None] = mapped_column(JSON)

    # URLs
    google_maps_url: Mapped[str | None] = mapped_column(String(1000))
    place_url: Mapped[str | None] = mapped_column(String(1000))

    # Sync tracking
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")

# ---------------------------------------------------
# Reviews (Includes fix for persistence)
# ---------------------------------------------------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Identifiers
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    review_url: Mapped[str | None] = mapped_column(String(1000))

    # Reviewer Information
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_id: Mapped[str | None] = mapped_column(String(255))
    author_url: Mapped[str | None] = mapped_column(String(1000))
    profile_photo_url: Mapped[str | None] = mapped_column(String(1000))
    author_profile_photo: Mapped[str | None] = mapped_column(String(1000))
    author_reviews_count: Mapped[int | None] = mapped_column(Integer)
    author_level: Mapped[int | None] = mapped_column(Integer)
    author_location: Mapped[str | None] = mapped_column(String(255))
    author_contributions: Mapped[int | None] = mapped_column(Integer)

    # Review Content
    rating: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    review_language: Mapped[str | None] = mapped_column(String(50))
    google_review_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    # 🚀 REFINED: Added for competitor fetching/persistence
    competitor_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_platform: Mapped[str | None] = mapped_column(String(100), default="Google")

    # Response / Reply Fields
    owner_answer: Mapped[str | None] = mapped_column(Text)
    owner_answer_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reply_text: Mapped[str | None] = mapped_column(Text)

    # Media
    review_photos: Mapped[list | None] = mapped_column(JSON)
    review_videos: Mapped[list | None] = mapped_column(JSON)

    # AI & Metrics
    review_likes: Mapped[int] = mapped_column(Integer, default=0)
    is_local_guide: Mapped[bool] = mapped_column(Boolean, default=False)
    sentiment_label: Mapped[str | None] = mapped_column(String(50))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    keywords: Mapped[list | None] = mapped_column(JSON)
    topic_tags: Mapped[list | None] = mapped_column(JSON)
    spam_score: Mapped[float | None] = mapped_column(Float)
    is_complaint: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_praise: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Aspect Scores
    aspect_rooms: Mapped[float | None] = mapped_column(Float)
    aspect_staff: Mapped[float | None] = mapped_column(Float)
    aspect_location: Mapped[float | None] = mapped_column(Float)
    aspect_value: Mapped[float | None] = mapped_column(Float)
    aspect_cleanliness: Mapped[float | None] = mapped_column(Float)
    aspect_food: Mapped[float | None] = mapped_column(Float)
    aspect_service: Mapped[float | None] = mapped_column(Float)
    aspect_amenities: Mapped[float | None] = mapped_column(Float)
    aspect_price: Mapped[float | None] = mapped_column(Float)
    aspect_atmosphere: Mapped[float | None] = mapped_column(Float)

    # Sync Tracking
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")

# ---------------------------------------------------
# Competitors
# ---------------------------------------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    place_id: Mapped[str | None] = mapped_column(String(512))
    rating: Mapped[float | None] = mapped_column(Float)
    reviews_count: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    google_maps_url: Mapped[str | None] = mapped_column(String(1000))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="competitors")

# ---------------------------------------------------
# Notifications & Logs
# ---------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default={})
    ip_address: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Config(Base):
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(1000), nullable=True)
