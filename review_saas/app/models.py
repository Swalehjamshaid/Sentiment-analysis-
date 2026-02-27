# filename: app/app/models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Company(Base):
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), index=True, nullable=False)
    address = Column(String(500))
    phone = Column(String(100))
    website = Column(String(255))
    google_place_id = Column(String(255))
    google_url = Column(String(500))
    state = Column(String(120))
    postal_code = Column(String(40))
    country = Column(String(120))
    rating = Column(Float)
    user_ratings_total = Column(Integer)
    types = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviews = relationship('Review', back_populates='company')

class Review(Base):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    source = Column(String(100), default='manual')
    text = Column(Text)
    sentiment = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    response_date = Column(DateTime)
    company = relationship('Company', back_populates='reviews')
    reply = relationship('Reply', back_populates='review', uselist=False)

class Reply(Base):
    __tablename__ = 'replies'
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey('reviews.id'))
    text = Column(Text)
    edited_text = Column(Text)
    status = Column(String(40))
    sent_at = Column(DateTime)
    responder_user_id = Column(Integer)
    is_public = Column(Boolean, default=False)
    review = relationship('Review', back_populates='reply')
