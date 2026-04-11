from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core.models import User
from app.core.security import get_password_hash, create_verification_token, decode_verification_token
from app.core.mailer import send_verification_email

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    """Handles Registration via Form and triggers Magic Link email."""
    
    # 1. Check if user already exists
    result = await db.execute(select(User).where(User.email == email))
    if result.scalars().first():
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "This email is already registered. Please log in."
        })

    # 2. Create new unverified user
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

    # 3. Generate Magic Link Token
    token = create_verification_token(new_user.email)
    
    # 4. Send Email via Resend
    try:
        await send_verification_email(new_user.email, token)
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "Account created, but email failed to send. Contact support."
        })

    return templates.TemplateResponse("register.html", {
        "request": request, 
        "success": "Account created! Please check your email for the magic link to log in."
    })


@router.get("/verify")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Verifies token and performs 'Magic' auto-login."""
    
    # 1. Decode Token
    email = decode_verification_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")

    # 2. Find and Verify User
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not user.email_verified:
        user.email_verified = True
        await db.commit()

    # 3. Auto-Login via Session Cookie
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_user", 
        value=user.email, 
        httponly=True, 
        max_age=86400, # 24 hours
        samesite="lax",
        secure=True # Railway uses HTTPS, so this is safe
    )
    return response
