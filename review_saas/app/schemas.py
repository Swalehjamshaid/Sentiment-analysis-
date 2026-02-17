# app/schemas.py
from pydantic import BaseModel, EmailStr, constr
from typing import Optional
from datetime import datetime

# --------- Users ---------
class UserCreate(BaseModel):
    full_name: constr(min_length=3, max_length=100)
    email: EmailStr
    password: constr(min_length=8)
    profile_picture_url: Optional[str]

class UserRead(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool
    profile_picture_url: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True

# --------- Companies ---------
class CompanyCreate(BaseModel):
    name: str
    google_place_id: Optional[str]
    maps_link: Optional[str]
    city: Optional[str]

class CompanyRead(BaseModel):
    id: int
    name: str
    google_place_id: Optional[str]
    maps_link: Optional[str]
    city: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

# --------- Reviews ---------
class ReviewRead(BaseModel):
    id: int
    review_text: Optional[str]
    star_rating: Optional[int]
    sentiment_category: Optional[str]
    sentiment_score: Optional[float]
    keywords: Optional[str]
    fetch_status: str
    fetch_date: datetime

    class Config:
        orm_mode = True

# --------- Suggested Replies ---------
class SuggestedReplyRead(BaseModel):
    id: int
    review_id: int
    suggested_text: str
    user_edited_text: Optional[str]
    status: str
    suggested_at: datetime
    sent_at: Optional[datetime]

    class Config:
        orm_mode = True
