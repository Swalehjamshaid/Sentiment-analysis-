
# filename: app/core/rate_limit.py
from __future__ import annotations
import time
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from app.core.config import settings

# naive in-memory rate limit: {key -> (reset_ts, count)}
_BUCKETS: Dict[str, Tuple[float,int]] = {}

def check_rate_limit(request: Request, key: str):
    now = time.time()
    window = settings.RATE_LIMIT_WINDOW_SEC
    max_req = settings.RATE_LIMIT_REQUESTS
    reset, count = _BUCKETS.get(key, (now + window, 0))
    if now > reset:
        reset, count = now + window, 0
    count += 1
    _BUCKETS[key] = (reset, count)
    if count > max_req:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
