# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.sql import func
from .db import Base

# --------- Users ---------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    profile_picture_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

# --------- Companies ---------
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    google_place_id = Column(String(100), nullable=True)
    maps_link = Column(String(300), nullable=True)
    city = Column(String(100), nullable=True)
    logo_url = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# --------- Reviews ---------
class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    review_text = Column(String(5000), nullable=True)
    star_rating = Column(Integer, nullable=True)
    review_date = Column(DateTime(timezone=True), nullable=True)
    reviewer_name = Column(String(100), nullable=True)
    reviewer_profile_url = Column(String(300), nullable=True)
    sentiment_category = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    keywords = Column(String(500), nullable=True)
    fetch_date = Column(DateTime(timezone=True), server_default=func.now())
    fetch_status = Column(String(50), default="Pending")

# --------- Suggested Replies ---------
class SuggestedReply(Base):
    __tablename__ = "suggested_replies"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=False)
    suggested_text = Column(String(500), nullable=False)
    user_edited_text = Column(String(500), nullable=True)
    status = Column(String(50), default="Draft")  # Draft / Sent
    suggested_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
