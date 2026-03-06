# File: /app/core/models.py
from __future__ import annotations
from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# --------------------
# Base and Schema version
# --------------------
Base = declarative_base()
SCHEMA_VERSION = "1.1"  # Increment this whenever you add/change models

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
    name = Column(String(255), nullable=False)
    address = Column(String(500))
    phone = Column(String(100))
    website = Column(String(255))
    category = Column(String(255))
    rating = Column(Float)
    total_reviews = Column(Integer)
    place_id = Column(String(255), unique=True, index=True)
    lat = Column(Float)
    lng = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --------------------
# Review Table (Outscraper reviews)
# --------------------
class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    author_name = Column(String(255))
    author_profile_photo = Column(String(500))
    rating = Column(Float)
    text = Column(Text)
    relative_time_description = Column(String(100))
    review_time = Column(DateTime)
    reply_text = Column(Text)
    reply_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="reviews")

Company.reviews = relationship("Review", order_by=Review.id, back_populates="company")

# --------------------
# AuditLog Table
# --------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    details = Column(JSON)  # Store any extra info
    ip_address = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

# --------------------
# Competitor Table (optional Outscraper competitor output)
# --------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    place_id = Column(String(255), nullable=True)
    rating = Column(Float)
    total_reviews = Column(Integer)
    lat = Column(Float)
    lng = Column(Float)

    company = relationship("Company", back_populates="competitors")

Company.competitors = relationship("Competitor", order_by=Competitor.id, back_populates="company")
