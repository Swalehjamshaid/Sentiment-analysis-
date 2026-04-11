# filename: app/routes/auth.py
from fastapi import APIRouter, Depends, Form, Request, Query, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import traceback

from app.core.db import get_db
from app.core.models import User
from app.core.security import get_password_hash, create_verification_token, decode_verification_token
from app.core.mailer import send_verification_email

router = APIRouter()

@router.post("/register")
async def register_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Import templates here to avoid circular import issues
    from app.main import templates

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Passwords do not match"}
        )

    email_clean = email.strip().lower()

    try:
        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email_clean))
        if result.scalars().first():
            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={"error": "This email is already registered."}
            )

        # Create new user (only using fields that most likely exist)
        new_user = User(
            name=name.strip(),
            email=email_clean,
            hashed_password=get_password_hash(password)
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        logger.info(f"✅ New user registered: {email_clean}")

        # Try to send verification email
        token = create_verification_token(new_user.email)
        try:
            await send_verification_email(new_user.email, token)
            success_msg = "Registration successful! Check your inbox for the magic login link."
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            success_msg = "Account created successfully!"

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"success": success_msg}
        )

    except Exception as e:
        await db.rollback()
        logger.error("❌ Registration Error")
        logger.error(traceback.format_exc())
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Something went wrong. Please try again."}
        )


@router.get("/verify")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    email = decode_verification_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Mark as verified if needed
    if hasattr(user, 'email_verified') and not user.email_verified:
        user.email_verified = True
        await db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
