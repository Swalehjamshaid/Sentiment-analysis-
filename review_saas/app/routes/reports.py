# FILE: app/routes/reports.py
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Review
from app.services.rbac import get_current_user

# Try service export if present, else fallback
try:
    from app.services.exports import export_reviews_report  # type: ignore
    HAS_EXPORT_SVC = True
except Exception:
    HAS_EXPORT_SVC = False

router = APIRouter(tags=["Reports & Exports"])


def _fallback_csv(db: Session, company_id: int, sdt: Optional[datetime], edt: Optional[datetime]):
    q = db.query(Review).filter(Review.company_id == company_id)
    if sdt: q = q.filter(Review.review_date >= sdt)
    if edt: q = q.filter(Review.review_date <= edt)
    rows = q.order_by(Review.review_date.asc()).all()
    out = io.StringIO()
    out.write("date,reviewer,rating,sentiment,emotion,text\n")
    for r in rows:
        d = (r.review_date.isoformat() if r.review_date else "") if r.review_date else ""
        out.write(f'"{d}","{(r.reviewer_name or "").replace(chr(34),"")}",{r.rating or ""},'
                  f'"{r.sentiment_category or ""}","{r.emotion_label or ""}","{(r.text or "").replace(chr(34),"")}"\n')
    stream = io.BytesIO(out.getvalue().encode("utf-8"))
    return stream, f"reviews_{company_id}.csv", "text/csv"


def _parse_iso(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/reports")
async def export_reviews(
    company_id: int = Query(...),
    format: str = Query("csv", regex="^(csv|xlsx|pdf)$"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not current_user:
        return PlainTextResponse("Unauthorized", status_code=401)

    sdt = _parse_iso(start)
    edt = _parse_iso(end)

    if HAS_EXPORT_SVC:
        stream, filename, media_type = export_reviews_report(db, company_id, format, sdt, edt)  # type: ignore
    else:
        # Minimal CSV fallback; Excel/PDF collapse to CSV for now
        stream, filename, media_type = _fallback_csv(db, company_id, sdt, edt)
        if format == "xlsx":
            filename = filename.replace(".csv", ".xlsx")
        if format == "pdf":
            filename = filename.replace(".csv", ".pdf")

    return StreamingResponse(stream, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })
