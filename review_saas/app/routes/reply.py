# FILE: app/routes/reply.py

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Review, Reply
from app.services.rbac import get_current_user, require_roles
from app.services.ai_insights import suggest_reply

router = APIRouter(tags=["Replies"])


@router.post("/reviews/{review_id}/reply/suggest")
def suggest_review_reply(
    review_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst"]))
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    suggestion = suggest_reply(
        text=review.text or "",
        rating=review.rating or 0,
        sentiment=review.sentiment_category or "Neutral",
        company_name=review.company.name if review.company else "your business"
    )
    # Return minimal JSON so XHR could be added later; but redirect for now
    return JSONResponse({"suggestion": suggestion})


@router.post("/reviews/{review_id}/reply")
def save_review_reply(
    request: Request,
    review_id: int,
    reply_text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager"]))
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Save a Reply row (Draft). If you post to provider, set status="Posted".
    rep = Reply(
        review_id=review.id,
        edited_text=(reply_text or "").strip(),
        status="Sent",
        sent_at=datetime.now(timezone.utc),
        responder_user_id=getattr(user, "id", None),
        is_public=True,
    )
    db.add(rep)
    db.commit()

    # Add a toast message
    request.session["flash_error"] = "Reply sent."  # reusing toast container; shows as success style if you adapt CSS
    return RedirectResponse(url="/dashboard", status_code=303)
