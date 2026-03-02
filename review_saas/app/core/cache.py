
# filename: app/core/cache.py
from __future__ import annotations
import time
from typing import Any, Dict, Tuple
from app.core.config import settings

_store: Dict[str, Tuple[float, Any]] = {}

def make_key(prefix: str, *parts: str) -> str:
    return prefix + '|' + '|'.join(parts)

def get(key: str):
    ttl = settings.CACHE_TTL_SEC
    item = _store.get(key)
    if not item:
        return None
    expires, val = item
    if time.time() > expires:
        _store.pop(key, None)
        return None
    return val

def set(key: str, value: Any):
    ttl = settings.CACHE_TTL_SEC
    _store[key] = (time.time() + ttl, value)
