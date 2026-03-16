# filename: app/routes/reviews.py

from __future__ import annotations

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.services.review import sync_all_companies_with_google, add_review
from app.core.db import get_session
from app.core.models import User

router = APIRouter(prefix="/reviews", tags=["reviews"])

# ---------------------------
# Auth Helper
# ---------------------------
def get_current_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

# ---------------------------
# Sync all companies with Google
# ---------------------------
@router.post("/sync-google")
async def sync_google_reviews(request: Request, session: AsyncSession = Depends(get_session)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    await sync_all_companies_with_google()
    return JSONResponse({"status": "success", "message": "All inactive companies synced with Google."})

# ---------------------------
# Add a review manually
# ---------------------------
@router.post("/add")
async def add_review_endpoint(
    request: Request,
    company_id: int = Form(...),
    author_name: str = Form(...),
    text: str = Form(...),
    rating: float = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    review = await add_review(
        company_id=company_id,
        author_name=author_name,
        text=text,
        rating=rating,
        session=session
    )
    return JSONResponse({
        "status": "success",
        "review_id": review.id,
        "company_id": company_id
    })

# ---------------------------
# Optional: Sync from Outscraper (if app.state.reviews_client is available)
# ---------------------------
@router.post("/sync-outscraper")
async def sync_outscraper_reviews(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    app = request.app
    if not hasattr(app.state, "reviews_client"):
        return JSONResponse({"status": "error", "message": "Outscraper client not configured."})

    # Example: just return empty array (you can expand this)
    return JSONResponse({"status": "success", "reviews": []})
