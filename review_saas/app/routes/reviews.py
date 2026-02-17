# app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import engine, get_db
from ..models import Review

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/")
def list_reviews(db: Session = Depends(get_db)):
    reviews = db.query(Review).all()
    return reviews
