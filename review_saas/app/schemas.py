
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str

    @field_validator('full_name')
    def name_len(cls, v):
        if not (1 <= len(v) <= 100):
            raise ValueError('Full name must be 1-100 characters')
        return v

    @field_validator('password')
    def password_strength(cls, v):
        import re
        if len(v) < 8 or not re.search(r'[A-Z]', v) or not re.search(r'[a-z]', v) or not re.search(r'\d', v) or not re.search(r'[^A-Za-z0-9]', v):
            raise ValueError('Password must be 8+ chars, include uppercase, lowercase, number, special char')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    status: str
    profile_pic_url: Optional[str]
    created_at: datetime
    last_login_at: Optional[datetime]
    email_verified: bool

class CompanyCreate(BaseModel):
    name: Optional[str] = None
    place_id: Optional[str] = None
    maps_url: Optional[str] = None
    city: Optional[str] = None

class CompanyOut(BaseModel):
    id: int
    name: Optional[str]
    place_id: Optional[str]
    maps_url: Optional[str]
    city: Optional[str]
    status: str
    logo_url: Optional[str]
    created_at: datetime

class ReviewOut(BaseModel):
    id: int
    company_id: int
    text: Optional[str]
    rating: Optional[int]
    review_datetime: Optional[datetime]
    reviewer_name: Optional[str]
    sentiment_category: Optional[str]
    sentiment_score: Optional[float]
    keywords: Optional[str]

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator('new_password')
    def password_strength(cls, v):
        import re
        if len(v) < 8 or not re.search(r'[A-Z]', v) or not re.search(r'[a-z]', v) or not re.search(r'\d', v) or not re.search(r'[^A-Za-z0-9]', v):
            raise ValueError('Password must be 8+ chars, include uppercase, lowercase, number, special char')
        return v

class ReplyCreate(BaseModel):
    review_id: int
    text: str

class DashboardFilters(BaseModel):
    company_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sentiment: Optional[str] = None
    rating: Optional[int] = None
