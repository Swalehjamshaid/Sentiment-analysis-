# FILE: app/routes/activity.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime
from sqlalchemy.orm import Session
import uuid
import json
import os

from ..db import get_db

# Try to import ActivityLog model if it exists.
# If not, we will still log to file and return success.
try:
    from ..models import ActivityLog  # type: ignore
except Exception:
    ActivityLog = None  # fallback when model/table not defined

router = APIRouter(prefix="/api", tags=["activity"])

class ActivityPayload(BaseModel):
    timestamp: Optional[str] = None
    action: str
    details: Optional[Dict[str, Any]] = None
    userAgent: Optional[str] = None
    path: Optional[str] = None
    sessionId: Optional[str] = None

def _safe_iso_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def _ensure_activity_dir() -> str:
    base = os.path.join("app_uploads", "activity")
    os.makedirs(base, exist_ok=True)
    return base

def _append_jsonl(record: Dict[str, Any]) -> None:
    base = _ensure_activity_dir()
    fname = f"activity-{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
    fpath = os.path.join(base, fname)
    with open(fpath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

@router.post("/activity")
def capture_activity(payload: ActivityPayload, db: Session = Depends(get_db)):
    """
    Collects UI telemetry from dashboard.html.
    - Attempts DB persist (if ActivityLog model exists).
    - Always appends to JSONL file for durability even if DB insert fails.
    """
    event_id = str(uuid.uuid4())
    received_at = _safe_iso_now()

    # Normalize timestamp
    ts = payload.timestamp
    try:
        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.utcnow()
    except Exception:
        ts_dt = datetime.utcnow()

    record = {
        "id": event_id,
        "timestamp": ts_dt.isoformat() + "Z",
        "action": payload.action,
        "details": payload.details or {},
        "userAgent": payload.userAgent,
        "path": payload.path,
        "sessionId": payload.sessionId,
        "receivedAt": received_at,
    }

    # File logging (always)
    try:
        _append_jsonl(record)
    except Exception as e:
        # File failures are non-fatal; continue
        pass

    # Optional DB logging if model exists
    if ActivityLog is not None:
        try:
            obj = ActivityLog(
                # NOTE: Depending on your model schema, you may have different field names.
                # Common fields are illustrated below; adjust if your ActivityLog differs.
                # If 'id' is auto-increment in your DB, remove 'id=event_id'.
                id=event_id if hasattr(ActivityLog, "id") else None,
                ts=ts_dt if hasattr(ActivityLog, "ts") else None,
                session_id=payload.sessionId if hasattr(ActivityLog, "session_id") else None,
                action=payload.action if hasattr(ActivityLog, "action") else None,
                details=payload.details if hasattr(ActivityLog, "details") else None,
                user_agent=payload.userAgent if hasattr(ActivityLog, "user_agent") else None,
                path=payload.path if hasattr(ActivityLog, "path") else None,
            )
            db.add(obj)
            db.commit()
        except Exception:
            db.rollback()
            # We already wrote to file, so do not fail the request.

    return {"ok": True, "id": event_id, "receivedAt": received_at}
