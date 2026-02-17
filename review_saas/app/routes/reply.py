from fastapi import APIRouter, HTTPException
    from sqlalchemy.orm import sessionmaker
    from ..db import engine
    from ..models import Reply, Review

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/reply", tags=["reply"])

    def suggest_for_text(text: str) -> str:
        t = (text or "").lower()
        if any(w in t for w in ["bad","terrible","awful","worst","poor"]):
            return "We’re sorry for your experience. Please contact support@example.com so we can make this right."[:500]
        if any(w in t for w in ["great","excellent","love","amazing","best"]):
            return "Thank you for the kind words! We appreciate your feedback and hope to see you again."[:500]
        return "Thanks for sharing your thoughts. We value your feedback and will keep improving."[:500]

    @router.post("/{review_id}")
    def save_reply(review_id: int, edited_text: str | None = None, mark_sent: bool = False):
        with SessionLocal() as s:
            rv = s.get(Review, review_id)
            if not rv:
                raise HTTPException(status_code=404, detail="Review not found")
            rep = s.query(Reply).filter(Reply.review_id==review_id).first()
            if not rep:
                rep = Reply(review_id=review_id, suggested_text=suggest_for_text(rv.text))
                s.add(rep)
            if edited_text is not None:
                rep.edited_text = edited_text[:500]
            if mark_sent:
                rep.status = "Sent"
            s.commit(); s.refresh(rep)
            return {"id": rep.id, "status": rep.status}