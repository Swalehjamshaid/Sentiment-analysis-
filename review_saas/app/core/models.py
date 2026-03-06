# File: /app/core/models.py
from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    Integer, String, DateTime, Float, ForeignKey, Boolean, JSON,
    UniqueConstraint, Text, ARRAY, create_engine, func
)
from datetime import datetime
import os
from dotenv import load_dotenv

# -------------------- CONFIG --------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")  # fallback

# 🚨 BUMP THIS TO FORCE FULL RESET
SCHEMA_VERSION = "2026-03-06-v1-outscreaper"

engine = create_engine(DATABASE_URL, echo=True)

# -------------------- BASE --------------------
class Base(DeclarativeBase):
    pass

# -------------------- USERS --------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_pic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    companies: Mapped[list["Company"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")

# -------------------- COMPANIES --------------------
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    google_place_id: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    formatted_address: Mapped[str | None] = mapped_column(String(512))
    address: Mapped[str | None] = mapped_column(String(512))
    vicinity: Mapped[str | None] = mapped_column(String(255))

    # Contact
    international_phone_number: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(512))

    # Categories
    category: Mapped[str | None] = mapped_column(String(255), index=True)
    types: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Location & hours
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    hours: Mapped[dict | None] = mapped_column(JSON)  # opening_hours object

    business_status: Mapped[str | None] = mapped_column(String(64))
    price_level: Mapped[int | None] = mapped_column(Integer)
    utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)

    # Ratings
    google_rating: Mapped[float | None] = mapped_column(Float)
    google_user_ratings_total: Mapped[int | None] = mapped_column(Integer)

    # Metadata
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Full JSON & photos
    google_data: Mapped[dict | None] = mapped_column(JSON)
    photos: Mapped[list[str] | None] = mapped_column(ARRAY(String(512)))
    editorial_summary: Mapped[str | None] = mapped_column(Text)

    # Google attributes
    curbside_pickup: Mapped[bool | None] = mapped_column(Boolean)
    delivery: Mapped[bool | None] = mapped_column(Boolean)
    takeout: Mapped[bool | None] = mapped_column(Boolean)
    reservable: Mapped[bool | None] = mapped_column(Boolean)
    serves_beer: Mapped[bool | None] = mapped_column(Boolean)
    serves_wine: Mapped[bool | None] = mapped_column(Boolean)
    outdoor_seating: Mapped[bool | None] = mapped_column(Boolean)
    wheelchair_accessible_entrance: Mapped[bool | None] = mapped_column(Boolean)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner: Mapped["User"] = relationship(back_populates="companies")
    reviews: Mapped[list["Review"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    competitors: Mapped[list["Competitor"]] = relationship(back_populates="company", cascade="all, delete-orphan")

# -------------------- REVIEWS --------------------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("company_id", "google_review_id", name="uq_review_company_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False)
    google_review_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # Reviewer info
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_url: Mapped[str | None] = mapped_column(String(512))
    profile_photo_url: Mapped[str | None] = mapped_column(String(512))
    reviewer_is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)

    # Review content
    rating: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    google_review_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), index=True)
    original_language: Mapped[str | None] = mapped_column(String(10))
    relative_time_description: Mapped[str | None] = mapped_column(String(100))
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_reply_text: Mapped[str | None] = mapped_column(Text)
    review_reply_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Advanced data
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    sentiment_label: Mapped[str | None] = mapped_column(String(20), index=True)
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    aspect_rating: Mapped[dict | None] = mapped_column(JSON)
    original_text: Mapped[str | None] = mapped_column(Text)
    translation: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list[str] | None] = mapped_column(ARRAY(String(512)))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    company: Mapped["Company"] = relationship(back_populates="reviews")

# -------------------- COMPETITOR ANALYSIS --------------------
class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("company_id", "place_id", name="uq_company_competitor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    place_id: Mapped[str] = mapped_column(String(512), nullable=False)
    rating: Mapped[float | None] = mapped_column(Float)
    user_ratings_total: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(512))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(512))
    google_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    company: Mapped["Company"] = relationship(back_populates="competitors")

# -------------------- NOTIFICATIONS --------------------
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship(back_populates="notifications")

# -------------------- AUDIT LOGS --------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship(back_populates="audit_logs")

# -------------------- RESET FUNCTION --------------------
def reset_db():
    """
    Drops all tables and creates new ones based on updated models.
    WARNING: Deletes ALL data!
    """
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating new tables...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete!")
