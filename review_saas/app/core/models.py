from __future__ import annotations
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# --------------------
# Base and Schema version
# --------------------
Base = declarative_base()
# Bumping version to reflect full Outscraper + Competitor Analysis compatibility
SCHEMA_VERSION = "5.0.0-outscraper-comprehensive"

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

    companies = relationship("Company", back_populates="owner")

# --------------------
# Company Table (Outscraper Business Info)
# --------------------
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Core Outscraper/Google Identifiers
    name = Column(String(255), nullable=False)
    place_id = Column(String(512), unique=True, index=True) 
    google_id = Column(String(255)) # Outscraper internal ID
    
    # Location & Contact
    full_address = Column(String(1000))
    city = Column(String(100))
    state = Column(String(100))
    postal_code = Column(String(20))
    phone = Column(String(100))
    website = Column(String(512))
    
    # Categorization & Attributes
    category = Column(String(255))
    sub_categories = Column(JSON) 
    type = Column(JSON) # Outscraper business types array
    
    # Performance & Sync
    rating = Column(Float)
    reviews_count = Column(Integer)
    lat = Column(Float)
    lng = Column(Float)
    
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")

# --------------------
# Review Table (Comprehensive Outscraper Output)
# --------------------
class Review(Base):
    __tablename__ = "reviews"
    # CRITICAL: Prevents duplicate storage of the same scrape data
    __table_args__ = (UniqueConstraint('company_id', 'google_review_id', name='_company_review_uc'),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Outscraper Identifiers
    google_review_id = Column(String(512), nullable=False, index=True)
    
    # Reviewer Info (Authority Tracking)
    author_name = Column(String(255))
    author_id = Column(String(255))
    author_profile_photo = Column(String(1024))
    author_reviews_count = Column(Integer) # Tracks if reviewer is a "Heavy Reviewer"
    author_level = Column(Integer) # Local Guide Level
    
    # Content
    rating = Column(Integer)
    text = Column(Text)
    review_language = Column(String(50))
    google_review_time = Column(DateTime) # UTC timestamp from Outscraper
    
    # Business Interaction
    owner_answer = Column(Text)
    owner_answer_timestamp = Column(DateTime)
    
    # Metrics
    review_likes = Column(Integer, default=0)
    review_photos = Column(JSON) # URLs of photos attached to this specific review
    
    # AI Enrichment Fields
    sentiment_label = Column(String(50)) # Positive/Negative/Neutral
    sentiment_score = Column(Float)
    keywords = Column(JSON) 

    created_at = Column(DateTime, default=datetime.utcnow)
    company = relationship("Company", back_populates="reviews")

# --------------------
# Competitor Table (Competitive Benchmarking)
# --------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    # Competitor Data
    name = Column(String(255), nullable=False)
    place_id = Column(String(512))
    rating = Column(Float)
    reviews_count = Column(Integer)
    
    # Distance and Location
    distance_km = Column(Float)
    lat = Column(Float)
    lng = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    company = relationship("Company", back_populates="competitors")

# --------------------
# AuditLog Table (Security Tracking)
# --------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(255), nullable=False)
    details = Column(JSON)
    ip_address = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
