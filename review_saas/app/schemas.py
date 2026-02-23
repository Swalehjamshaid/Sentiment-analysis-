# Filename: app/schemas.py

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# =========================================================
# COMPANY SCHEMAS
# =========================================================

class CompanyCreate(BaseModel):
    name: str
    place_id: Optional[str] = None
    maps_link: Optional[str] = None
    city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    city: Optional[str]
    status: str

    class Config:
        from_attributes = True


# =========================================================
# METRICS SCHEMAS
# =========================================================

class MetricsRequest(BaseModel):
    company_id: int
    start_date: Optional[datetime]
    end_date: Optional[datetime]


class RatingTrendPoint(BaseModel):
    date: datetime
    average_rating: float


class SentimentBreakdown(BaseModel):
    positive: int
    neutral: int
    negative: int


class MetricsResponse(BaseModel):
    total_reviews: int
    average_rating: float
    sentiment: SentimentBreakdown
    rating_trend: List[RatingTrendPoint]


# =========================================================
# REVIEW SCHEMAS
# =========================================================

class ReviewResponse(BaseModel):
    id: int
    reviewer_name: Optional[str]
    rating: Optional[int]
    text: Optional[str]
    sentiment_category: Optional[str]
    review_date: Optional[datetime]

    class Config:
        from_attributes = True


# =========================================================
# AI INSIGHTS SCHEMA
# =========================================================

class AIInsightResponse(BaseModel):
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]


# =========================================================
# RECENT REPLIES SCHEMA
# =========================================================

class RecentReplyResponse(BaseModel):
    review_id: int
    reviewer_name: Optional[str]
    review_text: Optional[str]
    rating: Optional[int]
    review_date: Optional[datetime]
    suggested_reply: Optional[str]
