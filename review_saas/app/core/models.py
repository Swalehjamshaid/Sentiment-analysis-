# filename: app/core/models.py
from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    Integer, String, Float, Text, Boolean, DateTime, JSON, 
    ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.db import Base

SCHEMA_VERSION = "25.0.6-added-company-cid-table"

class User(Base):
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
    companies = relationship("Company", back_populates="owner")

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(512), unique=True, index=True)
    internal_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_address: Mapped[Optional[str]] = mapped_column(String(1000))
    city: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[Optional[str]] = mapped_column(String(255))
    postal_code: Mapped[Optional[str]] = mapped_column(String(50))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    phone: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(512))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(255))
    sub_categories: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    type: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    business_status: Mapped[Optional[str]] = mapped_column(String(50))
    permanently_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    photos: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    working_hours: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    popular_times: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    business_attributes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    google_maps_url: Mapped[Optional[str]] = mapped_column(String(1000))
    place_url: Mapped[Optional[str]] = mapped_column(String(1000))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="company", cascade="all, delete-orphan")
    cid_info: Mapped[Optional["CompanyCID"]] = relationship("CompanyCID", back_populates="company", uselist=False)

class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    review_url: Mapped[Optional[str]] = mapped_column(String(1000))
    author_name: Mapped[Optional[str]] = mapped_column(String(255))
    author_id: Mapped[Optional[str]] = mapped_column(String(255))
    author_url: Mapped[Optional[str]] = mapped_column(String(1000))
    profile_photo_url: Mapped[Optional[str]] = mapped_column(String(1000))
    author_profile_photo: Mapped[Optional[str]] = mapped_column(String(1000))
    author_reviews_count: Mapped[Optional[int]] = mapped_column(Integer)
    author_level: Mapped[Optional[int]] = mapped_column(Integer)
    author_location: Mapped[Optional[str]] = mapped_column(String(255))
    author_contributions: Mapped[Optional[int]] = mapped_column(Integer)
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[Optional[str]] = mapped_column(Text)
    review_language: Mapped[Optional[str]] = mapped_column(String(50))
    google_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    competitor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_platform: Mapped[Optional[str]] = mapped_column(String(100), default="Google")
    owner_answer: Mapped[Optional[str]] = mapped_column(Text)
    owner_answer_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_reply_text: Mapped[Optional[str]] = mapped_column(Text)
    review_photos: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    review_videos: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    review_likes: Mapped[int] = mapped_column(Integer, default=0)
    is_local_guide: Mapped[bool] = mapped_column(Boolean, default=False)
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(50))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    keywords: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    topic_tags: Mapped[Optional[List[Any]]] = mapped_column(JSON)
    spam_score: Mapped[Optional[float]] = mapped_column(Float)
    is_complaint: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_praise: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
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
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")

class Competitor(Base):
    __tablename__ = "competitors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    place_id: Mapped[Optional[str]] = mapped_column(String(512))
    rating: Mapped[Optional[float]] = mapped_column(Float)
    reviews_count: Mapped[Optional[int]] = mapped_column(Integer)
    distance_km: Mapped[Optional[float]] = mapped_column(Float)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    google_maps_url: Mapped[Optional[str]] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    company = relationship("Company", back_populates="competitors")

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default={})
    ip_address: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Config(Base):
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

class CompanyCID(Base):
    __tablename__ = "company_cids"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    cid: Mapped[str] = mapped_column(String(100), nullable=False)
    place_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    company: Mapped["Company"] = relationship("Company", back_populates="cid_info")
