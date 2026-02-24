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
    
    # Requirements #3, #4, #5: Intelligence Fields
    sentiment_category: Optional[str] = None
    sentiment_score: Optional[float] = None
    detected_emotion: Optional[str] = None
    aspects: Optional[Dict[str, str]] = None 
    language: Optional[str] = None

class ReviewResponse(ReviewBase):
    id: int
    company_id: int
    model_config = ConfigDict(from_attributes=True)

# FIX: This is the missing class causing your crash
class ReviewListResponse(BaseModel):
    total: int
    page: int
    limit: int
    data: List[ReviewResponse]

class ResponseCreate(BaseModel):
    text: str
