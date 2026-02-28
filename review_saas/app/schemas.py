# FILE: app/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

# =========================================================
# ENUMS (optional but improves validation & docs)
# =========================================================
class StatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"
    archived = "archived"

class SentimentEnum(str, Enum):
    positive = "Positive"
    neutral = "Neutral"
    negative = "Negative"

class TrendSignalEnum(str, Enum):
    improving = "improving"
    stable = "stable"
    declining = "declining"
    insufficient_data = "insufficient_data"

# =========================================================
# COMPANY SCHEMAS
# =========================================================
class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Company/Business name")
    place_id: Optional[str] = Field(None, description="Google Places Place ID")
    maps_link: Optional[str] = None
    city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class CompanyResponse(BaseModel):
    id: int
    name: str
    place_id: Optional[str]
    city: Optional[str]
    status: str = Field(default="active")
    lat: Optional[float]
    lng: Optional[float]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    website: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CompanyListResponse(BaseModel):
    items: List[CompanyResponse]
    total: int
    page: int
    limit: int
    pages: int

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# REVIEW SCHEMAS
# =========================================================
class ReviewCreate(BaseModel):
    company_id: int
    reviewer_name: Optional[str]
    rating: Optional[int] = Field(None, ge=1, le=5)
    text: Optional[str]
    review_date: Optional[datetime]
    source: Optional[str] = "manual"


class ReviewResponse(BaseModel):
    id: int
    company_id: int
    reviewer_name: Optional[str]
    rating: Optional[int] = Field(None, ge=1, le=5)
    text: Optional[str]
    sentiment_category: Optional[SentimentEnum]
    review_date: Optional[datetime]
    fetch_at: Optional[datetime]
    source_url: Optional[str]

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# METRICS / SUMMARY SCHEMAS
# =========================================================
class MetricsRequest(BaseModel):
    company_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class RatingTrendPoint(BaseModel):
    date: str  # ISO date string (YYYY-MM-DD or YYYY-MM)
    average_rating: Optional[float]
    review_count: int = 0


class SentimentBreakdown(BaseModel):
    positive: int = 0
    neutral: int = 0
    negative: int = 0


class TrendInfo(BaseModel):
    signal: TrendSignalEnum = TrendSignalEnum.insufficient_data
    delta: float = 0.0
    description: Optional[str]


class MetricsResponse(BaseModel):
    company_name: str
    total_reviews: int = 0
    average_rating: float = 0.0
    sentiment: SentimentBreakdown
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: str = Field(..., pattern="^(Low|Medium|High)$")
    rating_trend: List[RatingTrendPoint]
    trend: TrendInfo
    window_start: str  # ISO datetime
    window_end: str    # ISO datetime
    last_updated: datetime

    model_config = ConfigDict(from_attributes=False)


# =========================================================
# AI INSIGHTS / RECOMMENDATIONS
# =========================================================
class RecommendationItem(BaseModel):
    area: str
    count: int
    priority: str = Field(..., pattern="^(High|Medium|Low)$")
    action: str


class AIInsightResponse(BaseModel):
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    key_themes: List[str]
    recommendations: List[RecommendationItem]
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=False)


# =========================================================
# SUGGESTED REPLIES (optional future feature)
# =========================================================
class SuggestedReplyResponse(BaseModel):
    review_id: int
    reviewer_name: Optional[str]
    review_text: Optional[str]
    rating: Optional[int]
    review_date: Optional[datetime]
    sentiment: Optional[SentimentEnum]
    suggested_reply: Optional[str]
    tone: Optional[str] = Field(None, description="e.g. 'empathetic', 'professional', 'apologetic'")
    confidence: Optional[float] = Field(None, ge=0, le=1)

    model_config = ConfigDict(from_attributes=False)
