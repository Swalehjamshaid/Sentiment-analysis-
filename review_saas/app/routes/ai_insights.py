# filename: app/routes/ai_insights.py

from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.routes.dashboard import get_dashboard_insights  # reuse the same logic

router = APIRouter(prefix="/api/ai", tags=["AI Insights (Compat)"])

def _safe_date(val: Optional[str], default: datetime) -> datetime:
    try:
        if not val:
            return default
        d = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return default

@router.get("/insights")
async def ai_insights(
    company_id: int = Query(...),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_session),
):
    """
    Compatibility endpoint to support legacy frontends that call /api/ai/insights.
    Delegates to the same insights payload as /api/dashboard/insights.
    """
    start_d = _safe_date(start, datetime.now(timezone.utc) - timedelta(days=365))
    end_d = _safe_date(end, datetime.now(timezone.utc))

    payload = await get_dashboard_insights(session, company_id, start_d, end_d)
    if not payload:
        # mirror dashboard behavior
        return {"status": "no_data"}
    return payload
