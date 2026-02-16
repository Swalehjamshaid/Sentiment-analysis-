from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_admin: bool
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class CompanyCreate(BaseModel):
    name: str
    google_place_id: Optional[str] = None
    maps_link: Optional[str] = None
    city: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class CompanyOut(BaseModel):
    id: int
    name: str
    google_place_id: Optional[str]
    maps_link: Optional[str]
    city: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    class Config:
        from_attributes = True

class ReviewOut(BaseModel):
    id: int
    review_text: Optional[str]
    star_rating: Optional[int]
    review_date: Optional[datetime]
    reviewer_name: Optional[str]
    sentiment: Optional[str]
    keywords: Optional[str]
    class Config:
        from_attributes = True

class ReplyOut(BaseModel):
    review_id: int
    suggested_reply: Optional[str]
    edited_reply: Optional[str]
    class Config:
        from_attributes = True

class DashboardSummary(BaseModel):
    total_reviews: int
    average_rating: float | None
    pct_positive: float
    pct_neutral: float
    pct_negative: float
    ratings_trend: List[tuple]