# filename: app/routes/auth.py
import os
import resend
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.db import get_db
from app.core.models import User, VerificationToken
from passlib.context import CryptContext
from loguru import logger

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Use the Resend API Key from your environment variables
resend.api_key = os.getenv("RESEND_API_KEY")

@router.post("/register")
async def register_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Basic Validation
    if password != confirm_password:
        return RedirectResponse(url="/register?error=Passwords+do+not+match", status_code=303)

    # 2. Check if user already exists
    result = await db.execute(select(User).where(User.email == email.strip().lower()))
    existing_user = result.scalars().first()
    if existing_user:
        return RedirectResponse(url="/register?error=Email+already+registered", status_code=303)

    try:
        # 3. Create the New User (is_verified defaults to False)
        new_user = User(
            name=name,
            email=email.strip().lower(),
            hashed_password=pwd_context.hash(password),
            is_verified=False
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # 4. Create a unique Verification Token (utilizing your model)
        token_entry = VerificationToken(user_id=new_user.id)
        db.add(token_entry)
        await db.commit()
        await db.refresh(token_entry)

        # 5. Send Verification Email via Resend
        # Note: 'onboarding@resend.dev' only sends to your own email unless domain is verified
        verify_url = f"{request.base_url}api/auth/verify?token={token_entry.token}"
        
        resend.Emails.send({
            "from": os.getenv("MAIL_FROM", "onboarding@resend.dev"),
            "to": new_user.email,
            "subject": "Verify your Review Intel AI Account",
            "html": f"""
                <div style="font-family: sans-serif; max-width: 600px; margin: auto;">
                    <h2 style="color: #4f46e5;">Welcome to Review Intel AI!</h2>
                    <p>Hi {name},</p>
                    <p>Please click the button below to verify your email and activate your account:</p>
                    <a href="{verify_url}" style="display: inline-block; background-color: #6366f1; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold;">Verify My Account</a>
                    <p style="margin-top: 20px; font-size: 12px; color: #6b7280;">If the button doesn't work, copy and paste this link: <br> {verify_url}</p>
                </div>
            """
        })
        
        logger.info(f"✅ User registered and verification email sent to: {new_user.email}")
        return RedirectResponse(url="/login?success=Check+your+email+to+verify+your+account", status_code=303)

    except Exception as e:
        logger.error(f"❌ Registration process failed: {str(e)}")
        return RedirectResponse(url="/register?error=Something+went+wrong.+Please+try+again.", status_code=303)

@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    # Look for the token in the database
    result = await db.execute(select(VerificationToken).where(VerificationToken.token == token))
    db_token = result.scalars().first()
    
    if not db_token:
        return RedirectResponse(url="/login?error=Invalid+or+expired+verification+link", status_code=303)
    
    # Find the associated user
    user_result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = user_result.scalars().first()
    
    if user:
        user.is_verified = True
        await db.delete(db_token)  # Delete token after successful use
        await db.commit()
        return RedirectResponse(url="/login?success=Account+verified!+You+can+now+login.", status_code=303)
            
    return RedirectResponse(url="/login?error=User+not+found", status_code=303)
