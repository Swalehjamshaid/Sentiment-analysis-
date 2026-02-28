from pydantic import BaseModel, EmailStr, Field
    from typing import Optional
    from datetime import datetime

    class UserCreate(BaseModel):
        full_name: str = Field(..., max_length=100)
        email: EmailStr
        password: str = Field(..., min_length=8)

    class UserLogin(BaseModel):
        email: EmailStr
        password: str

    class CompanyIn(BaseModel):
        name: Optional[str] = None
        place_id: Optional[str] = None
        maps_link: Optional[str] = None
        city: Optional[str] = None

    class ReviewOut(BaseModel):
        id: int
        rating: int
        text: str | None
        review_at: datetime | None
        sentiment: str | None

        class Config:
            from_attributes = True