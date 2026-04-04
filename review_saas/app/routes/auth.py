# filename: app/routes/auth.py
import logging
import os
from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from starlette.templating import Jinja2Templates

# --- REFINED ALIGNMENT IMPORTS ---
from app.core.db import get_db
from app.core.models import User, VerificationToken
from app.core.config import settings

router = APIRouter()

# Dynamic pathing for templates to ensure alignment in Docker/Railway
CURRENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(CURRENT_DIR, "templates"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger("app.auth")

# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------

def send_verification_email(email: str, token: str):
    """Logs verification link to console (Mock SMTP)."""
    verify_link = f"{settings.APP_BASE_URL}/api/auth/verify?token={token}"
    logger.info("--------------------------------------------------")
    logger.info(f"📧 VERIFICATION EMAIL FOR: {email}")
    logger.info(f"🔗 LINK: {verify_link}")
    logger.info("--------------------------------------------------")

# ----------------------------------------------------------
# ROUTES
# ----------------------------------------------------------

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
async def register_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    email_clean = email.strip().lower()
    
    # Duplicate email check
    res = await db.execute(select(User).where(User.email == email_clean))
    if res.scalars().first():
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "This email is already registered."
        })

    # Hash password and create user
    hashed = pwd_context.hash(password)
    new_user = User(name=name, email=email_clean, hashed_password=hashed)
    db.add(new_user)
    
    # Using flush to get the ID without fully committing yet
    await db.flush()

    # Generate token
    token_obj = VerificationToken(user_id=new_user.id)
    db.add(token_obj)
    await db.commit()

    # Send Mock Email
    send_verification_email(email_clean, token_obj.token)
    
    return templates.TemplateResponse("verify_email_sent.html", {
        "request": request, 
        "email": email_clean
    })

@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Handles account verification via token link."""
    # Find token
    res = await db.execute(
        select(VerificationToken).where(VerificationToken.token == token)
    )
    token_rec = res.scalars().first()

    if not token_rec:
        return RedirectResponse(
            url="/login?error=Invalid or expired verification link."
        )

    # Find User associated with token
    user_res = await db.execute(
        select(User).where(User.id == token_rec.user_id)
    )
    user = user_res.scalars().first()
    
    if user:
        # Update user status
        user.is_verified = True
        # Cleanup used token
        await db.delete(token_rec)
        await db.commit()
    
    return RedirectResponse(
        url="/login?message=Account verified successfully! Please login."
    )
