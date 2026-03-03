# filename: app/core/models.py
from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, Float, ForeignKey, Boolean, JSON, UniqueConstraint, func, Text
from datetime import datetime

class Base(DeclarativeBase):
    pass

# -------------------- USERS & AUTH --------------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    
    role: Mapped[str] = mapped_column(String(20), default="viewer") 
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_pic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    companies: Mapped[list["Company"]] = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


# -------------------- COMPANIES --------------------
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    place_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    hours: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    
    # Aggregated Analytics (Fixed: Matches DB schema)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    
    # CRITICAL: We calculate sentiment from the Review table in dashboard.py, 
    # so we remove avg_sentiment from here to stop the "UndefinedColumn" crash.
    
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    google_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship("User", back_populates="companies")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="company", cascade="all, delete-orphan")


# -------------------- REVIEWS & SENTIMENT --------------------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("company_id", "source_id", name="uq_review_source"),)
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True) 
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True) 
    keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship("Company", back_populates="reviews")


# -------------------- NOTIFICATIONS & AUDIT --------------------
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64)) 
    message: Mapped[str] = mapped_column(String(1000))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="notifications")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(128)) 
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="audit_logs")
