# filename: app/dependencies.py
from typing import Dict, Any, AsyncGenerator
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Level 3 imports Level 1 and Level 2
from app.core.db import SessionLocal
from app.core.models import User

# 1. Database Dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# 2. Authentication Dependency (The fix for your Line 30 error)
async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Level 3: Logic to extract user from session.
    Imported by Level 4 (Routes).
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user

# 3. Specific Logic Dependency
async def get_active_company_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        # Additional logic can go here
        pass
    return current_user
