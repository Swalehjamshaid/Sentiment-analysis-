
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, Text,
    ForeignKey, JSON, UniqueConstraint, Index
)
from datetime import datetime, timezone

Base = declarative_base()

def now_utc():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    profile_pic_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    place_id = Column(String(128), nullable=True)
    maps_link = Column(String(512), nullable=True)
    google_url = Column(String(512), nullable=True)
    address = Column(String(512), nullable=True)
    city = Column(String(128), nullable=True)
    state = Column(String(128), nullable=True)
    postal_code = Column(String(32), nullable=True)
    country = Column(String(128), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    rating = Column(Float, nullable=True)
    user_ratings_total = Column(Integer, nullable=True)
    types = Column(String(512), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    last_sync_message = Column(String(512), nullable=True)
    parent_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    owner = relationship("User", back_populates="companies")
    parent = relationship("Company", remote_side=[id], backref="branches")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    __table_args__ = (
        Index("idx_company_owner_status", "owner_id", "status"),
        Index("idx_company_place_id", "place_id"),
        Index("idx_company_created", "created_at"),
        Index("idx_company_parent", "parent_id"),
        Index("idx_company_city", "city"),
    )

class ReviewSource(Base):
    __tablename__ = "review_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    description = Column(String(255), nullable=True)
    base_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint("name", name="uq_source_name"),)

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(Integer, ForeignKey("review_sources.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(64), nullable=True)  # convenience string e.g., 'google'
    external_id = Column(String(128), nullable=True)
    text = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    review_date = Column(DateTime, nullable=True)
    response_date = Column(DateTime, nullable=True)
    reviewer_name = Column(String(255), nullable=True)
    reviewer_avatar = Column(String(255), nullable=True)
    sentiment_category = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    sentiment_confidence = Column(Float, nullable=True)
    emotion_label = Column(String(32), nullable=True)
    emotion_scores = Column(JSON, nullable=True)
    aspect_summary = Column(JSON, nullable=True)
    keywords = Column(String(512), nullable=True)
    topics = Column(JSON, nullable=True)
    language = Column(String(10), nullable=True)
    language_confidence = Column(Float, nullable=True)
    translated_text = Column(Text, nullable=True)
    journey_stage = Column(String(32), nullable=True)
    fetch_at = Column(DateTime, default=now_utc, nullable=False)
    fetch_status = Column(String(20), default="Success", nullable=False)
    is_spam_suspected = Column(Boolean, default=False, nullable=False)
    anomaly_score = Column(Float, nullable=True)
    company = relationship("Company", back_populates="reviews")
    source_rel = relationship("ReviewSource")
    __table_args__ = (
        UniqueConstraint("company_id", "external_id", name="uq_review_company_ext"),
        Index("idx_review_company_date", "company_id", "review_date"),
        Index("idx_review_rating", "rating"),
        Index("idx_review_sentiment", "sentiment_category"),
        Index("idx_review_language", "language"),
        Index("idx_review_source", "source_id"),
        Index("idx_review_anomaly", "is_spam_suspected", "anomaly_score"),
    )

class Reply(Base):
    __tablename__ = "replies"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=True)
    edited_text = Column(Text, nullable=True)
    status = Column(String(32), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    responder_user_id = Column(Integer, nullable=True)
    is_public = Column(Boolean, default=True, nullable=False)

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)

