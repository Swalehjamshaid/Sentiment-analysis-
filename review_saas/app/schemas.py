
from typing import Optional, List
from pydantic import BaseModel

class ReviewOut(BaseModel):
    id: int
    company_id: int
    source: Optional[str] = None
    external_id: Optional[str] = None
    text: Optional[str] = None
    rating: Optional[int] = None
    review_date: Optional[str] = None
    reviewer_name: Optional[str] = None
    sentiment_category: Optional[str] = None
    sentiment_score: Optional[float] = None

    class Config:
        orm_mode = True

class ReviewListResponse(BaseModel):
    total: int
    page: int
    limit: int
    data: List[ReviewOut]
