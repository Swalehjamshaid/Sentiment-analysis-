from __future__ import annotations
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# --------------------
# Base and Schema version
# --------------------
Base = declarative_base()
# Bumping version to reflect deep Outscraper integration
SCHEMA_VERSION = "4.0.0-outscraper-v2"

# --------------------
# User Table
# --------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# --------------------
# Company Table (Outscraper business info)
# --------------------
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Core Outscraper Data
    name = Column(String(255), nullable=False)
    place_id = Column(String(512), unique=True, index=True) # Essential for Outscraper syncing
    address = Column(String(500))
    full_address = Column(String(1000))
    phone = Column(String(100))
    website = Column(String(512))
    
    # Categorization
    category = Column(String(255))
    sub_categories = Column(JSON) # Outscraper provides multiple types
    
    # Performance Stats
    rating = Column(Float)
    total_reviews = Column(Integer)
    price_level = Column(Integer)
    
    # Map coordinates
    lat = Column(Float)
    lng = Column(Float)
    
    # Sync Metadata
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")

# --------------------
# Review Table (Comprehensive Outscraper Output)
# --------------------
class Review(Base):
    __tablename__ = "reviews"
    # Prevent duplicate reviews being saved for the same business
    __table_args__ = (UniqueConstraint('company_id', 'google_review_id', name='_company_review_uc'),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Outscraper Identifiers
    google_review_id = Column(String(512), nullable=False, index=True)
    
    # Reviewer Info
    author_name = Column(String(255))
    author_id = Column(String(255))
    author_profile_photo = Column(String(1024))
    author_reviews_count = Column(Integer) # Outscraper tells us how active the user is
    
    # Review Content
    rating = Column(Float)
    text = Column(Text)
    language = Column(String(50))
    review_time = Column(DateTime) # Actual UTC time from Outscraper
    relative_time_description = Column(String(100))
    
    # Owner Response (Critical for Reputation SaaS)
    reply_text = Column(Text)
    reply_time = Column(DateTime)
    
    # Metadata
    review_likes = Column(Integer, default=0)
    review_photos = Column(JSON) # Array of photo URLs attached to review
    
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="reviews")
    analysis = relationship("ReviewExtra", back_populates="review", uselist=False, cascade="all, delete-orphan")

# --------------------
# ReviewExtra (AI/Sentiment Analysis)
# --------------------
class ReviewExtra(Base):
    __tablename__ = "review_extras"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), unique=True)
    
    sentiment_label = Column(String(50)) # Positive, Negative, Neutral
    sentiment_score = Column(Float)
    keywords = Column(JSON) # Extracted topics
    
    created_at = Column(DateTime, default=datetime.utcnow)

    review = relationship("Review", back_populates="analysis")

# --------------------
# Competitor Table
# --------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Competitor Identity
    name = Column(String(255), nullable=False)
    place_id = Column(String(512))
    
    # Competitive Metrics (Calculated or scraped)
    rating = Column(Float)
    total_reviews = Column(Integer)
    lat = Column(Float)
    lng = Column(Float)
    
    # Distance from your main business
    distance_km = Column(Float)

    company = relationship("Company", back_populates="competitors")

# --------------------
# AuditLog Table
# --------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(255), nullable=False)
    details = Column(JSON)
    ip_address = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

# --------------------
# DATABASE RESET UTILITY
# --------------------
def reset_db(engine):
    """Drops and re-creates tables. USE WITH CAUTION."""
    print(f"Applying Schema Version: {SCHEMA_VERSION}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✓ Database successfully updated with Outscraper-compatible schema.")
