# FILE: app/schemas.py

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime

class ReviewBase(BaseModel):
    external_id: Optional[str] = None
    text: Optional[str] = None
    rating: Optional[float] = None
    review_date: Optional[datetime] = None
    reviewer_name: Optional[str] = None
    source_type: Optional[str] = "google"

    sentiment_category: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_confidence: Optional[float] = None
    emotion_label: Optional[str] = None
    aspect_summary: Optional[Dict[str, Dict]] = None
    topics: Optional[Dict[str, float]] = None
    keywords: Optional[str] = None
    language: Optional[str] = None

class ReviewResponse(ReviewBase):
    id: int
    company_id: int
    model_config = ConfigDict(from_attributes=True)

class ReviewListResponse(BaseModel):
    total: int
    page: int
    limit: int
    data: List[ReviewResponse]
