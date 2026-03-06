# File: /app/core/models.py
from __future__ import annotations
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# Track schema version → increment whenever models change
SCHEMA_VERSION = "3.0.0"

Base = declarative_base()

# =======================
# Core Tables
# =======================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    notifications = relationship("Notification", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    address = Column(String(300))
    phone = Column(String(50))
    website = Column(String(200))
    google_place_id = Column(String(100), unique=True)
    category = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reviews = relationship("Review", back_populates="company")
    competitors = relationship("Competitor", back_populates="company")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    author_name = Column(String(200))
    rating = Column(Float)
    text = Column(Text)
    time_created = Column(DateTime)
    source = Column(String(50))  # Google, Outscraper, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="reviews")
    extras = relationship("ReviewExtra", back_populates="review")


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    competitor_name = Column(String(200))
    competitor_place_id = Column(String(100))
    distance_km = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="competitors")
    extras = relationship("CompetitorExtra", back_populates="competitor")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(200))
    table_name = Column(String(100))
    record_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


class Config(Base):
    __tablename__ = "config"

    key = Column(String(50), primary_key=True)
    value = Column(String(100))


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String(200))
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")


# =======================
# Outscraper Output Tables
# =======================

class PlaceDetails(Base):
    __tablename__ = "place_details"

    id = Column(Integer, primary_key=True)
    place_id = Column(String(100), unique=True)
    name = Column(String(200))
    address = Column(String(300))
    phone = Column(String(50))
    website = Column(String(200))
    rating = Column(Float)
    total_reviews = Column(Integer)
    category = Column(String(100))
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewExtra(Base):
    __tablename__ = "review_extras"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"))
    sentiment = Column(String(50))  # Positive, Neutral, Negative
    language = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    review = relationship("Review", back_populates="extras")


class CompetitorExtra(Base):
    __tablename__ = "competitor_extras"

    id = Column(Integer, primary_key=True)
    competitor_id = Column(Integer, ForeignKey("competitors.id", ondelete="CASCADE"))
    category = Column(String(100))
    rating = Column(Float)
    total_reviews = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    competitor = relationship("Competitor", back_populates="extras")
