# FILE: app/routes/reply.py
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Review, Reply
from app.services.rbac import get_current_user
from app.services import ai_insights as ai_svc

router = APIRouter(prefix="/reviews", tags=["Replies"])


@router.post("/{review_id}/reply/suggest")
async def suggest_reply(
    review_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Generates AI suggested reply and stores as Draft."""
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    suggestion = ai_svc.suggest_reply(review) or "Thank you for your review!"
    rep = Reply(
        review_id=review.id,
        suggested_text=suggestion,
        status="Draft",
        suggested_at=datetime.now(timezone.utc),
        responder_user_id=current_user.id,
    )
    db.add(rep)
    db.commit()
    # Redirect back to dashboard for the same company
    return RedirectResponse(f"/dashboard?company_id={review.company_id}", status_code=303)


@router.post("/{review_id}/reply")
async def post_reply(
    review_id: int,
    reply_text: Optional[str] = Form(default=""),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Saves user's reply (Send button)."""
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    rep = Reply(
        review_id=review.id,
        edited_text=(reply_text or "").strip(),
        status="Sent",
        suggested_at=datetime.now(timezone.utc),
        sent_at=datetime.now(timezone.utc),
        responder_user_id=current_user.id,
        is_public=True,
    )
    db.add(rep)
    db.commit()
    return RedirectResponse(f"/dashboard?company_id={review.company_id}", status_code=303)
