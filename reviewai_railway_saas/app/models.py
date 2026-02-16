from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120))
    email = Column(String(200), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_admin = Column(Boolean, default=False)

    companies = relationship("Company", back_populates="owner")

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(255), nullable=False)
    google_place_id = Column(String(255))
    maps_link = Column(Text)
    city = Column(String(120))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    contact_email = Column(String(200))
    contact_phone = Column(String(50))

    owner = relationship("User", back_populates="companies")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), index=True)
    review_text = Column(Text)
    star_rating = Column(Integer)
    review_date = Column(DateTime(timezone=True))
    reviewer_name = Column(String(255))
    sentiment = Column(String(20))
    keywords = Column(Text)
    date_fetched = Column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="reviews")
    reply = relationship("Reply", back_populates="review", uselist=False, cascade="all, delete-orphan")

class Reply(Base):
    __tablename__ = "replies"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), unique=True)
    suggested_reply = Column(Text)
    edited_reply = Column(Text)

    review = relationship("Review", back_populates="reply")