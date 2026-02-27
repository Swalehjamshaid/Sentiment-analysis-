
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime
from sqlalchemy.orm import Session
import uuid
import json
import os

from app.db import get_db

try:
    from app.models import ActivityLog  # type: ignore
except Exception:
    ActivityLog = None  # type: ignore

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
        f.write(json.dumps(record, ensure_ascii=False) + "
")

@router.post("/activity")
def capture_activity(payload: ActivityPayload, db: Session = Depends(get_db)):
    event_id = str(uuid.uuid4())
    received_at = _safe_iso_now()
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

    try:
        _append_jsonl(record)
    except Exception:
        pass

    if ActivityLog is not None:
        try:
            obj = ActivityLog()
            db.add(obj); db.commit()
        except Exception:
            db.rollback()

    return {"ok": True, "id": event_id, "receivedAt": received_at}
