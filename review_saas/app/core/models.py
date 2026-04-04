from __future__ import annotations
import secrets
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    Integer, String, Float, Text, Boolean, DateTime, 
    JSON, ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

# Import the shared Base from db.py
from app.core.db import Base

# Stegman Versioning: Incremented to ensure auto-reset for the verification system
SCHEMA_VERSION = "25.0.8-auth-verification-system"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(50), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    companies = relationship("Company", back_populates="owner")
    verification_token = relationship("VerificationToken", back_populates="user", uselist=False, cascade="all, delete-orphan")

class VerificationToken(Base):
    __tablename__ = "verification_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_urlsafe(32), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="verification_token")

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(512), unique=True, index=True)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    cid_info = relationship("CompanyCID", back_populates="company", uselist=False, cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("company_id", "google_review_id", name="_company_review_uc"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(255))
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[Optional[str]] = mapped_column(Text)
    google_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(50))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")

class CompanyCID(Base):
    __tablename__ = "company_cids"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), unique=True)
    cid: Mapped[str] = mapped_column(String(100), nullable=False)
    company = relationship("Company", back_populates="cid_info")

class Config(Base):
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(1000))
