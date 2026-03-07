from __future__ import annotations
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# ---------------------------------------------------
# Base
# ---------------------------------------------------
Base = declarative_base()

# Bumped version to force a clean database recreation with new columns
SCHEMA_VERSION = "6.0.7-outscraper-full"

# ---------------------------------------------------
# Users
# ---------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    email_verified = Column(Boolean, default=False)
    profile_pic = Column(String(1000), nullable=True)
    role = Column(String(50), default="editor")

    created_at = Column(DateTime, default=datetime.utcnow)
    companies = relationship("Company", back_populates="owner")

# ---------------------------------------------------
# Companies
# ---------------------------------------------------
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    # Basic info
    name = Column(String(255), nullable=False)
    address = Column(String(1000), nullable=True) 

    # Google Identifiers
    google_place_id = Column(String(512), unique=True, index=True)
    internal_place_id = Column(String(255), nullable=True) 
    google_id = Column(String(255), nullable=True)

    # Location Details
    full_address = Column(String(1000))
    city = Column(String(255))
    state = Column(String(255))
    postal_code = Column(String(50))
    country = Column(String(100))
    lat = Column(Float)
    lng = Column(Float)

    # Contact
    phone = Column(String(255))
    website = Column(String(512))
    email = Column(String(255))

    # Categories & Stats
    category = Column(String(255))
    sub_categories = Column(JSON)
    type = Column(JSON)
    business_status = Column(String(50))
    permanently_closed = Column(Boolean, default=False)
    rating = Column(Float, default=0.0)
    reviews_count = Column(Integer, default=0)

    # Media & Hours
    photos = Column(JSON)
    working_hours = Column(JSON)
    popular_times = Column(JSON)
    business_attributes = Column(JSON)

    # URLs
    google_maps_url = Column(String(1000))
    place_url = Column(String(1000))

    # Sync tracking
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")

# ---------------------------------------------------
# Reviews
# ---------------------------------------------------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Identifiers
    google_review_id = Column(String(512), nullable=False, index=True)
    review_url = Column(String(1000))

    # Reviewer Information
    author_name = Column(String(255))
    author_id = Column(String(255))
    author_url = Column(String(1000))
    
    # NEW FIELDS: Fixes TypeError: 'profile_photo_url' is an invalid keyword argument
    profile_photo_url = Column(String(1000), nullable=True) 
    author_profile_photo = Column(String(1000), nullable=True) 
    
    author_reviews_count = Column(Integer)
    author_level = Column(Integer)

    # Review Content
    rating = Column(Integer)
    text = Column(Text)
    review_language = Column(String(50))
    google_review_time = Column(DateTime)

    # NEW FIELD: Fixes mapping for owner response in google_reviews.py
    owner_answer = Column(Text)
    review_reply_text = Column(Text, nullable=True) 
    owner_answer_timestamp = Column(DateTime)

    # Metrics
    review_likes = Column(Integer, default=0)
    review_photos = Column(JSON)
    is_local_guide = Column(Boolean, default=False)

    # AI Processing
    sentiment_label = Column(String(50))
    sentiment_score = Column(Float, default=0.0)
    keywords = Column(JSON)
    topic_tags = Column(JSON)
    spam_score = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)
    company = relationship("Company", back_populates="reviews")

# ---------------------------------------------------
# Competitors
# ---------------------------------------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    place_id = Column(String(512))
    rating = Column(Float)
    reviews_count = Column(Integer)
    distance_km = Column(Float)
    lat = Column(Float)
    lng = Column(Float)
    google_maps_url = Column(String(1000))
    created_at = Column(DateTime, default=datetime.utcnow)
    company = relationship("Company", back_populates="competitors")

# ---------------------------------------------------
# Notifications & Audit
# ---------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String(255))
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(255), nullable=False)
    meta = Column(JSON, default={})
    ip_address = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class Config(Base):
    __tablename__ = "config"
    key = Column(String(255), primary_key=True)
    value = Column(String(255))
