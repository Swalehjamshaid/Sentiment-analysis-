# filename: app/core/models.py
from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    Integer, String, Float, Text, Boolean, DateTime, 
    JSON, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

# Use the shared Base from your DB module to avoid circular imports
from app.core.db import Base

# ---------------------------------------------------
# SCHEMA VERSION
# ---------------------------------------------------
SCHEMA_VERSION = "25.0.6-added-company-cid-table"

# ---------------------------------------------------
# Users Table
# ---------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    companies = relationship("Company", back_populates="owner")


# ---------------------------------------------------
# Companies Table
# ---------------------------------------------------
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    
    # Basic info used by the Dashboard
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Google Identifiers (Used by Autocomplete & Scraper)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(512), unique=True, index=True)
    
    # Cached Stats for KPI cards
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Sync tracking
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    
    # Link to CompanyCID for deep scraping
    cid_info: Mapped[Optional["CompanyCID"]] = relationship(
        "CompanyCID", back_populates="company", uselist=False, cascade="all, delete-orphan"
    )


# ---------------------------------------------------
# Reviews Table
# ---------------------------------------------------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Google Review Data
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(255))
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[Optional[str]] = mapped_column(Text)
    google_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # AI Sentiment & Emotions (Required for Radar/Trend charts)
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(50)) # e.g., "Positive", "Negative"
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    emotion_label: Mapped[Optional[str]] = mapped_column(String(50))   # e.g., "Happy", "Angry", "Neutral"
    
    # Sync Tracking
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")


# ---------------------------------------------------
# CompanyCID Table (The Missing Link)
# ---------------------------------------------------
class CompanyCID(Base):
    """Stores the Google Maps CID for deep scraping logic."""
    __tablename__ = "company_cids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    cid: Mapped[str] = mapped_column(String(100), nullable=False)
    place_id: Mapped[Optional[str]] = mapped_column(String(512))
    
    company: Mapped["Company"] = relationship("Company", back_populates="cid_info")


# ---------------------------------------------------
# Config Table (For Stegman Rule tracking)
# ---------------------------------------------------
class Config(Base):
    """Stores system-wide metadata like current schema version."""
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(1000))
