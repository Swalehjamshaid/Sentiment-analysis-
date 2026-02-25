# FILE: app/routes/companies.py
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Callable

import googlemaps
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Review
from app.services.rbac import get_current_user
from app.services import ai_insights as ai_svc

router = APIRouter(tags=["Companies & Sync"])
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def _get_google_api_key() -> Optional[str]:
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _db_factory_from_dep() -> Callable[[], Session]:
    def _factory():
        return next(get_db())
    return _factory


def sync_google_reviews_task(company_id: int, place_id: str, db_session_factory: Callable[[], Session]):
    """Background task to fetch latest Google reviews."""
    api_key = _get_google_api_key()
    if not api_key:
        log.error("Missing GOOGLE_MAPS_API_KEY / GOOGLE_API_KEY; abort Google sync.")
        return

    db: Session = db_session_factory()
    try:
        client = googlemaps.Client(key=api_key)
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            log.warning("Company %s not found", company_id)
            return

        result = client.place(place_id=place_id, fields=["reviews", "rating"])
        revs = (result.get("result") or {}).get("reviews") or []
        new_count = 0

        for rev in revs:
            ext_id = str(rev.get("time") or "")
            if not ext_id:
                continue
            exists = (
                db.query(Review)
                .filter(Review.company_id == company_id, Review.external_id == ext_id)
                .first()
            )
            if exists:
                continue

            when = datetime.fromtimestamp(rev.get("time", 0), tz=timezone.utc) if rev.get("time") else datetime.now(timezone.utc)
            obj = Review(
                company_id=company_id,
                external_id=ext_id,
                text=rev.get("text"),
                rating=int(rev.get("rating", 0) or 0),
                review_date=when,
                reviewer_name=rev.get("author_name"),
                reviewer_avatar=rev.get("profile_photo_url"),
            )
            db.add(obj)
            new_count += 1

        company.last_synced_at = datetime.now(timezone.utc)
        company.last_sync_status = "success"
        db.commit()
        log.info("Google sync complete company_id=%s new=%s", company_id, new_count)

        # Optional: detect anomalies quickly
        all_reviews = (
            db.query(Review)
            .filter(Review.company_id == company_id)
            .order_by(Review.review_date.desc())
            .all()
        )
        _alerts = ai_svc.detect_anomalies(all_reviews)
        if _alerts:
            log.warning("[Anomaly] company_id=%s alerts=%s", company_id, len(_alerts))

    except Exception as e:
        log.exception("Google Sync error: %s", e)
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                company.last_sync_status = "failed"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


@router.post("/companies/create")
async def create_company(
    request: Request,
    name: str,
    place_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Matches the 'Add Company' form in sidebar."""
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    obj = Company(
        owner_id=current_user.id,
        name=name.strip(),
        place_id=(place_id or "").strip() or None,
        created_at=datetime.now(timezone.utc),
        last_sync_status=None,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return RedirectResponse(f"/dashboard?company_id={obj.id}", status_code=303)


@router.post("/companies/{company_id}/delete")
async def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Matches sidebar delete form action."""
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Allow owner/admin deletion
    if company.owner_id != current_user.id and getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    db.delete(company)
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/sync/run")
async def run_sync_get(
    company_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    GET shim to match `Run Sync Now` link in dashboard template.
    Triggers Google sync if Place ID is set, then redirects back to dashboard.
    """
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not company.place_id:
        return RedirectResponse(f"/dashboard?company_id={company_id}", status_code=303)

    background_tasks.add_task(
        sync_google_reviews_task,
        company_id,
        company.place_id,
        _db_factory_from_dep(),
    )
    return RedirectResponse(f"/dashboard?company_id={company_id}", status_code=303)


@router.post("/companies/{company_id}/sync")
async def trigger_sync_post(
    company_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """POST sync trigger (API style)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.place_id:
        raise HTTPException(status_code=400, detail="Google Place ID is not set")
    background_tasks.add_task(
        sync_google_reviews_task,
        company_id,
        company.place_id,
        _db_factory_from_dep(),
    )
    return JSONResponse({"message": "Sync started"})
