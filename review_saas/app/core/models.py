# filename: review_saas/app/core/models.py
from __future__ import annotations
import secrets
from datetime import datetime
from typing import Optional, List

# SQLAlchemy imports
from sqlalchemy import (
    Integer, String, Float, Text, Boolean, DateTime,
    ForeignKey, UniqueConstraint, func
)
from sqlalchemy.orm import (
    relationship,
    Mapped,
    mapped_column
)

# ✅ THE ALIGNMENT FIX: 
# We import the Base from Level 1 (db.py) to ensure all models 
# share the same metadata and engine context.
from app.core.db import Base

# Schema version for lifespan migration control in main.py
SCHEMA_VERSION = "26.0.9-comprehensive-v2-final"

# ===========================
# USER MODEL
# ===========================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Auth & Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(50), default="user")

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    companies: Mapped[List["Company"]] = relationship(
        "Company",
        back_populates="owner",
        cascade="all, delete-orphan"
    )

    verification_token: Mapped[Optional["VerificationToken"]] = relationship(
        "VerificationToken",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )


# ===========================
# VERIFICATION TOKEN
# ===========================
class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    token: Mapped[str] = mapped_column(
        String(128),
        default=lambda: secrets.token_urlsafe(32),
        unique=True,
        index=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="verification_token")


# ===========================
# COMPANY MODEL
# ===========================
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(1000))
    google_place_id: Mapped[Optional[str]] = mapped_column(
        String(512),
        unique=True,
        index=True
    )

    # Stats
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)

    # Sync Control
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    owner: Mapped[Optional["User"]] = relationship("User", back_populates="companies")

    reviews: Mapped[List["Review"]] = relationship(
        "Review",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    cid_info: Mapped[Optional["CompanyCID"]] = relationship(
        "CompanyCID",
        back_populates="company",
        uselist=False,
        cascade="all, delete-orphan"
    )


# ===========================
# REVIEW MODEL
# ===========================
class Review(Base):
    __tablename__ = "reviews"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "google_review_id",
            name="_company_review_uc"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Google Data
    google_review_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(255))
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[Optional[str]] = mapped_column(Text)
    google_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # AI Analysis
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(50))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    emotion_label: Mapped[Optional[str]] = mapped_column(String(50))

    # Relationship
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")


# ===========================
# COMPANY CID MODEL
# ===========================
class CompanyCID(Base):
    __tablename__ = "company_cids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )

    cid: Mapped[str] = mapped_column(String(100), nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="cid_info")


# ===========================
# CONFIG MODEL
# ===========================
class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String(1000))
