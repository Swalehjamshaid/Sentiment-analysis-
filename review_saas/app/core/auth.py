from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core.models import User
from app.core.security import get_password_hash, create_verification_token, decode_verification_token
from app.core.mailer import send_verification_email

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(name: str, email: str, password: str, db: AsyncSession = Depends(get_db)):
    """Handles User Registration and sends verification email."""
    
    # 1. Check for existing user
    result = await db.execute(select(User).where(User.email == email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email is already registered.")

    # 2. Create new user with email_verified=False (matching your User model)
    new_user = User(
        name=name,
        email=email,
        hashed_password=get_password_hash(password),
        email_verified=False,
        is_active=True
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # 3. Generate token and send email
    token = create_verification_token(new_user.email)
    await send_verification_email(new_user.email, token)

    return {"message": "User registered successfully. Please check your email to verify your account."}


@router.get("/verify")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Verifies the JWT token, updates the DB, and redirects to dashboard."""
    
    # 1. Decode and Validate Token
    email = decode_verification_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="The verification link is invalid or has expired.")

    # 2. Find User
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 3. Mark as verified
    if not user.email_verified:
        user.email_verified = True
        await db.commit()

    # 4. Redirect to Dashboard with a session cookie (Auto-login)
    # Note: In production, you'd usually set a proper Session JWT here
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_user", 
        value=user.email, 
        httponly=True, 
        max_age=3600, 
        samesite="lax"
    )
    return response
