# filename: app/core/models.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, Float, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship, Mapped, mapped_column

# ✅ IMPORT BASE FROM DB.PY
from app.core.db import Base

SCHEMA_VERSION = "2026-04-05-FRESH-START-COMPLETE"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    companies: Mapped[List["Company"]] = relationship("Company", back_populates="owner")

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    google_place_id: Mapped[str] = mapped_column(String(512), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    owner: Mapped["User"] = relationship("User", back_populates="companies")
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="company")

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    google_review_id: Mapped[str] = mapped_column(String(512), unique=True)
    author_name: Mapped[str] = mapped_column(String(255))
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    sentiment_label: Mapped[str] = mapped_column(String(50), nullable=True)
    
    company: Mapped["Company"] = relationship("Company", back_populates="reviews")

class Config(Base):
    __tablename__ = "config"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(1000))
