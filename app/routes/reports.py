
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io
import csv

from app.db import get_db
from app.models import Review
from app.services.rbac import get_current_user, require_roles

try:
    from app.services.exports import export_reviews_report  # type: ignore
except Exception:
    export_reviews_report = None  # type: ignore

router = APIRouter(tags=["Reports"])

@router.get("/reports")
def export_reviews(
    company_id: int = Query(...),
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst", "admin"]))
):
    if export_reviews_report:
        stream, filename, media_type = export_reviews_report(db, company_id, format, None, None)
        return StreamingResponse(stream, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        })

    rows = db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_date.desc()).all()
    buff = io.StringIO()
    writer = csv.writer(buff)
    writer.writerow(["date", "reviewer", "rating", "sentiment", "emotion", "text"])
    for r in rows:
        writer.writerow([
            r.review_date.isoformat() if r.review_date else "",
            r.reviewer_name or "",
            r.rating or "",
            r.sentiment_category or "",
            r.emotion_label or "",
            (r.text or "").replace("
", " ").replace("", " ")
        ])
    data = io.BytesIO(buff.getvalue().encode("utf-8"))
    filename = f"reviews_{company_id}.csv"
    return StreamingResponse(data, media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })
