# filename: app/core/models.py
from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
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
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

# Use the shared Base from the DB module
from app.core.db import Base

# ---------------------------------------------------
# SCHEMA VERSION (Updated to trigger the new table)
# ---------------------------------------------------
SCHEMA_VERSION = "25.0.6-added-company-cid-table"

# ---------------------------------------------------
# Users Table
# ---------------------------------------------------
class User(Base):
    """
    Represents the system users/administrators.
    """
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_pic: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="editor")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    companies = relationship("Company", back_populates="owner")


# ---------------------------------------------------
# Companies Table
# ---------------------------------------------------
class Company(Base):
    """
    Represents business locations being tracked for reviews and competition.
    """
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Google Identifiers
    google_place_id: Mapped[Optional[str]] = mapped_column(String(512), unique=True, index=True)
    internal_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Location Details
    full_address: Mapped[Optional[str]] = mapped_column(String(1000))
    city: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[Optional[str]] = mapped_column(String(255))
    postal_code: Mapped[Optional[str]] = mapped_column(String(50))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)

    # Contact
    phone: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(512))
    email: Mapped[Optional[str]] = mapped_column(String(255))

    # Categories & Stats
    category: Mapped[Optional[str]] = mapped_column(String(255))
    sub_categories: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    type: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    business_status: Mapped[Optional[str]] = mapped_column(String(50))
    permanently_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)

    # Media & Hours
    photos: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    working_hours: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    popular_times: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    business_attributes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # URLs
    google_maps_url: Mapped[Optional[str]] = mapped_column(String(1000))
    place_url: Mapped[Optional[str]] = mapped_column(String(1000))

    # Sync tracking
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now()
    )

    # Relationships
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")
    
    # Link to CompanyCID
    cid_info: Mapped[Optional["CompanyCID"]] = relationship(
        "CompanyCID", 
        back_populates="company", 
        uselist=False
    )


# ---------------------------------------------------
# Reviews Table
# ---------------------------------------------------
class Review(Base):
    """
    Persisted review records with deep metadata for sentiment and aspect analysis.
    """
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # Identifiers
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    review_url: Mapped[Optional[str]] = mapped_column(String(1000))

    # Reviewer Info
    author_name: Mapped[Optional[str]] = mapped_column(String(255))
    author_id: Mapped[Optional[str]] = mapped_column(String(255))
    author_url: Mapped[Optional[str]] = mapped_column(String(1000))
    profile_photo_url: Mapped[Optional[str]] = mapped_column(String(1000))
    author_profile_photo: Mapped[Optional[str]] = mapped_column(String(1000))
    author_reviews_count: Mapped[Optional[int]] = mapped_column(Integer)
    author_level: Mapped[Optional[int]] = mapped_column(Integer)
    author_location: Mapped[Optional[str]] = mapped_column(String(255))
    author_contributions: Mapped[Optional[int]] = mapped_column(Integer)

    # Review Content
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[Optional[str]] = mapped_column(Text)
    review_language: Mapped[Optional[str]] = mapped_column(String(50))
    google_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Competitor & Source
    competitor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_platform: Mapped[Optional[str]] = mapped_column(String(100), default="Google")

    # Response / Reply
    owner_answer: Mapped[Optional[str]] = mapped_column(Text)
    owner_answer_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_reply_text: Mapped[Optional[str]] = mapped_column(Text)

    # Media
    review_photos: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    review_videos: Mapped[Optional[List[Any]]] = mapped_column(JSON)

    # AI & Metrics
    review_likes: Mapped[int] = mapped_column(Integer, default=0)
    is_local_guide: Mapped[bool] = mapped_column(Boolean, default=False)
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(50))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    keywords: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    topic_tags: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    spam_score: Mapped[Optional[float]] = mapped_column(Float)
    is_complaint: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_praise: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Aspect Scores
    aspect_rooms: Mapped[Optional[float]] = mapped_column(Float)
    aspect_staff: Mapped[Optional[float]] = mapped_column(Float)
    aspect_location: Mapped[Optional[float]] = mapped_column(Float)
    aspect_value: Mapped[Optional[float]] = mapped_column(Float)
    aspect_cleanliness: Mapped[Optional[float]] = mapped_column(Float)
    aspect_food: Mapped[Optional[float]] = mapped_column(Float)
    aspect_service: Mapped[Optional[float]] = mapped_column(Float)
    aspect_amenities: Mapped[Optional[float]] = mapped_column(Float)
    aspect_price: Mapped[Optional[float]] = mapped_column(Float)
    aspect_atmosphere: Mapped[Optional[float]] = mapped_column(Float)

    # Sync Tracking
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now()
    )

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")


# ---------------------------------------------------
# Competitors Table
# ---------------------------------------------------
class Competitor(Base):
    """
    Represents local business competitors discovered near a company location.
    """
    __tablename__ = "competitors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    place_id: Mapped[Optional[str]] = mapped_column(String(512))
    rating: Mapped[Optional[float]] = mapped_column(Float)
    reviews_count: Mapped[Optional[int]] = mapped_column(Integer)
    distance_km: Mapped[Optional[float]] = mapped_column(Float)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    google_maps_url: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    company = relationship("Company", back_populates="competitors")


# ---------------------------------------------------
# Notifications Table
# ---------------------------------------------------
class Notification(Base):
    """
    User alerts for new reviews, low ratings, or system events.
    """
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------
# Audit Logs Table
# ---------------------------------------------------
class AuditLog(Base):
    """
    Records sensitive system changes and user actions for security compliance.
    """
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    ip_address: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------
# Config Table
# ---------------------------------------------------
class Config(Base):
    """
    General system settings and version tracking metadata.
    """
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)


# ---------------------------------------------------
# CompanyCID Table
# ---------------------------------------------------
class CompanyCID(Base):
    """
    Stores the Google Maps CID (data_id) for each company.
    """
    __tablename__ = "company_cids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    company_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("companies.id", ondelete="CASCADE"), 
        unique=True, 
        nullable=False,
        index=True
    )
    
    cid: Mapped[str] = mapped_column(String(100), nullable=False)
    place_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now()
    )

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="cid_info")
