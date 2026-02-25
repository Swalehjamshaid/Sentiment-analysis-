# FILE: review_saas/app/services/rbac.py

from __future__ import annotations

from typing import List, Optional, Dict, Any
import os

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

# Optional DB imports; code will still work without DB
try:
    from ..db import get_db
    from .. import models
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    get_db = None  # type: ignore
    models = None  # type: ignore
    Session = None  # type: ignore

# ---------------------------------------------------------------------
# OAuth2 scheme (keeps compatibility with your existing code)
# ---------------------------------------------------------------------
# If you mounted a token endpoint at /auth/login or /auth/token, adjust tokenUrl below.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

# ---------------------------------------------------------------------
# Dev tokens (compatible with your existing "fake_users_db" approach)
# ---------------------------------------------------------------------
DEV_TOKENS: Dict[str, Dict[str, Any]] = {
    "admin_token": {"id": 1, "username": "admin", "role": "admin", "roles": ["admin", "user"]},
    "user_token": {"id": 2, "username": "user", "role": "user", "roles": ["user"]},
}

# ---------------------------------------------------------------------
# Lightweight token decoder:
# - Accepts dev tokens above
# - If you add JWT later, replace this with a real verifier
# ---------------------------------------------------------------------
def decode_token(raw_token: str) -> Optional[Dict[str, Any]]:
    """
    Minimal token decoder:
      - Accepts known dev tokens (admin_token, user_token)
      - Optionally, parse simple 'username:role' csv dev token for quick demos
      - Placeholder for future JWT verification
    """
    if not raw_token:
        return None

    # Dev tokens
    if raw_token in DEV_TOKENS:
        return DEV_TOKENS[raw_token]

    # Super-simple dev token: "username:role"
    if ":" in raw_token and len(raw_token.split(":", 1)) == 2:
        username, role = raw_token.split(":", 1)
        role = role.strip() or "user"
        return {
            "id": None,
            "username": username.strip(),
            "role": role,
            "roles": [role, "user"] if role != "user" else ["user"],
        }

    # TODO: Plug real JWT verification here
    # Example (pseudo):
    # try:
    #     payload = jwt.decode(raw_token, JWT_PUBLIC_KEY, algorithms=["RS256"])
    #     return {"id": payload["sub"], "username": payload["name"], "roles": payload.get("roles", [])}
    # except jwt.PyJWTError:
    #     return None

    return None


# ---------------------------------------------------------------------
# Helpers to extract token from Bearer or Cookie
# ---------------------------------------------------------------------
def _extract_token(request: Request, bearer: Optional[str]) -> Optional[str]:
    """
    Priority:
      1) Authorization: Bearer <token>
      2) Cookie: session=<token>
    """
    if bearer:
        return bearer
    cookie_token = request.cookies.get("session")
    if cookie_token:
        return cookie_token
    return None


# ---------------------------------------------------------------------
# Public dependencies
# ---------------------------------------------------------------------
async def get_current_user(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Optional["Session"] = Depends(get_db) if get_db else None,
):
    """
    Returns an authenticated user object or raises 401.
    - Accepts Bearer tokens and 'session' cookie.
    - If DB is available, tries to load the user record.
    - Otherwise returns a dict with roles like your old code.
    """
    raw = _extract_token(request, bearer_token)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )

    token_data = decode_token(raw)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # If we have a DB and models, try to load a real user record
    if db is not None and models is not None:
        try:
            user_id = token_data.get("id")
            username = token_data.get("username")
            user: Optional["models.User"] = None

            if user_id:
                user = db.query(models.User).filter(models.User.id == user_id).first()
            elif username:
                # If your schema has a username column; adjust as needed.
                if hasattr(models.User, "username"):
                    user = db.query(models.User).filter(models.User.username == username).first()

            if user:
                return user  # ORM user object with role/permissions from DB
        except Exception:
            # If DB lookup fails, we still allow dev token dict to proceed
            pass

    # Fallback: return a dict (compatible with your previous rbac)
    return token_data


async def get_current_user_or_none(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Optional["Session"] = Depends(get_db) if get_db else None,
):
    """
    Same as get_current_user but returns None if not authenticated.
    Useful for pages that render for both anon & logged-in users.
    """
    try:
        return await get_current_user(request, bearer_token, db)  # type: ignore[arg-type]
    except HTTPException:
        return None


def require_roles(required_roles: List[str]):
    """
    FastAPI dependency to enforce that the user has at least one of the required roles.
    Works with both ORM user objects and dict-based dev users.
    Usage:
        @router.get("/admin")
        async def admin_only(user = Depends(require_roles(["admin"]))):
            ...
    """
    async def _checker(
        user=Depends(get_current_user),
    ):
        # Extract roles from ORM or dict
        roles: List[str] = []
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated"
            )

        # ORM user: prefer explicit 'role' or 'roles' field if present
        if hasattr(user, "roles") and isinstance(getattr(user, "roles"), list):
            roles = list(getattr(user, "roles"))
        elif hasattr(user, "role") and getattr(user, "role"):
            roles = [getattr(user, "role")]
        elif isinstance(user, dict):
            roles = user.get("roles") or ([user.get("role")] if user.get("role") else [])

        # Normalize to strings
        roles = [str(r).lower() for r in roles if r]

        # Allow 'admin' to pass any gate
        if "admin" in roles:
            return user

        # Any match satisfies the requirement
        needed = [r.lower() for r in required_roles]
        if not any(r in roles for r in needed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {required_roles}",
            )
        return user

    return _checker
