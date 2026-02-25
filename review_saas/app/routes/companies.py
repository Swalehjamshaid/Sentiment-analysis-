# FILE: app/routes/companies.py

import os
import logging
from typing import Optional, Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Review
from app.services.rbac import get_current_user, require_roles
from app.services.ai_insights import analyze_reviews, hour_heatmap, detect_anomalies

# Optional googlemaps; fallback safely if not present
try:
    import googlemaps  # type: ignore
except Exception:  # pragma: no cover
    googlemaps = None  # type: ignore

router = APIRouter(tags=["Business Intelligence & Google API"])
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _get_google_api_key() -> Optional[str]:
    # Prefer GOOGLE_MAPS_API_KEY but allow GOOGLE_API_KEY too
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_API_KEY")

def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────
# Centralized Google sync task (background)
# ─────────────────────────────────────────────────────────────

def _sync_google_reviews_task(company_id: int, place_id: str, db_session_factory: Callable[[], Session]):
    api_key = _get_google_api_key()
    if not api_key or not googlemaps:
        log.error("Google API client not available or key missing. Skipping sync.")
        return

    gmaps = googlemaps.Client(key=api_key)
    db: Session = db_session_factory()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            log.warning("Company %s not found", company_id)
            return

        # Fetch reviews (basic fields)
        result = gmaps.place(place_id=place_id, fields=['reviews', 'rating'])
        reviews_data = (result or {}).get('result', {}).get('reviews', []) or []
        new_count = 0

        for rev in reviews_data:
            # Google exposes epoch seconds as 'time' – use as external id to dedupe
            ext_id = str(rev.get('time')) if rev.get('time') else None
            if not ext_id:
                continue

            exists = db.query(Review).filter(
                Review.company_id == company_id,
                Review.external_id == ext_id
            ).first()
            if exists:
                continue

            review_dt = datetime.fromtimestamp(rev.get('time'), tz=timezone.utc) if rev.get('time') else datetime.now(timezone.utc)
            db.add(Review(
                company_id=company_id,
                external_id=ext_id,
                text=rev.get('text'),
                rating=int(rev.get('rating', 0) or 0),
                review_date=review_dt,
                reviewer_name=rev.get('author_name'),
                reviewer_avatar=rev.get('profile_photo_url'),
                # Keep sentiment fields empty here; can be enriched later by AI pipeline
            ))
            new_count += 1

        company.last_synced_at = datetime.now(timezone.utc)
        company.last_sync_status = "success"
        company.last_sync_message = f"Synced {new_count} new Google reviews"

        db.commit()
        log.info("[Google Sync] company_id=%s new=%s", company_id, new_count)

        # Optional anomaly pass
        all_reviews = db.query(Review).filter(Review.company_id == company_id).all()
        alerts = detect_anomalies(all_reviews)
        if alerts:
            log.warning("[Anomalies] company_id=%s alerts=%s", company_id, len(alerts))

    except Exception as e:
        db.rollback()
        log.exception("Google sync failed: %s", e)
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                company.last_sync_status = "failed"
                company.last_sync_message = str(e)[:500]
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# CRUD: Create/Delete to match template forms
# ─────────────────────────────────────────────────────────────

@router.post("/companies/create")
def create_company(
    request: Request,
    name: str,
    place_id: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "admin"]))
):
    if not name.strip():
        request.session["flash_error"] = "Company name is required."
        return RedirectResponse(url="/dashboard", status_code=303)

    company = Company(
        owner_id=getattr(user, "id", None),
        name=name.strip(),
        place_id=place_id.strip() if place_id else None,
        created_at=datetime.now(timezone.utc)
    )
    db.add(company)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/companies/{company_id}/delete")
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "admin"]))
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    # Owner check (adjust as your RBAC needs)
    if getattr(user, "role", "owner") != "admin" and company.owner_id != getattr(user, "id", None):
        raise HTTPException(status_code=403, detail="Not allowed")
    db.delete(company)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


# ─────────────────────────────────────────────────────────────
# Sync: GET shim to match template link /sync/run?company_id=...
# ─────────────────────────────────────────────────────────────

@router.get("/sync/run")
def run_sync_now(
    company_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "admin"]))
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.place_id:
        raise HTTPException(status_code=400, detail="Google Place ID not configured")

    def _db_factory() -> Session:
        return next(get_db())

    background_tasks.add_task(_sync_google_reviews_task, company.id, company.place_id, _db_factory)
    return RedirectResponse(url="/dashboard", status_code=303)


# ─────────────────────────────────────────────────────────────
# Optional: dashboard JSON payload (if consumed elsewhere)
# ─────────────────────────────────────────────────────────────

@router.get("/companies/{company_id}/dashboard")
def company_dashboard_payload(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _: None = Depends(require_roles(["owner", "manager", "analyst", "admin"]))
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    # (Optional) parse start/end ISO and filter …
    reviews = q.order_by(Review.review_date.desc()).all()

    report = analyze_reviews(reviews, company, None, None)
    heat = hour_heatmap(reviews, None, None)
    dist = {str(i): 0 for i in range(1, 6)}
    for r in reviews:
        if r.rating in (1, 2, 3, 4, 5):
            dist[str(int(r.rating))] += 1

    return JSONResponse({
        "company": {"id": company.id, "name": company.name, "last_sync": company.last_synced_at.isoformat() if company.last_synced_at else None},
        "executive_summary": report.get("executive_summary", {}),
        "visuals": {"rating_distribution": dist, "heatmap": heat},
    })
