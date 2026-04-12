# filename: app/routes/auth.py
import os
import resend
from fastapi import APIRouter, Depends, Form, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
from loguru import logger

# Internal imports - assuming these match your project structure
from app.core.db import get_db
from app.core.models import User, VerificationToken

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Resend API Configuration
resend.api_key = os.getenv("RESEND_API_KEY")

# --- Helper Functions ---

def send_verification_email(name: str, email: str, verify_url: str):
    """
    Sends the verification email. This is defined as a sync function
    so it can be safely offloaded to a background thread by FastAPI.
    """
    try:
        resend.Emails.send({
            "from": os.getenv("MAIL_FROM", "onboarding@resend.dev"),
            "to": email,
            "subject": "Verify your Review Intel AI Account",
            "html": f"""
                <div style="font-family: sans-serif; max-width: 600px; margin: auto; border: 1px solid #e5e7eb; padding: 20px; border-radius: 12px;">
                    <h2 style="color: #4f46e5;">Welcome to Review Intel AI!</h2>
                    <p>Hi {name},</p>
                    <p>Please click the button below to verify your email and activate your account:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verify_url}" style="display: inline-block; background-color: #6366f1; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold;">Verify My Account</a>
                    </div>
                    <p style="margin-top: 20px; font-size: 12px; color: #6b7280;">If the button doesn't work, copy and paste this link: <br> {verify_url}</p>
                    <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                    <p style="font-size: 10px; color: #9ca3af;">If you did not create this account, please ignore this email.</p>
                </div>
            """
        })
        logger.info(f"📧 Verification email dispatched to {email}")
    except Exception as e:
        logger.error(f"⚠️ Failed to send email to {email}: {str(e)}")

# --- Routes ---

@router.post("/register")
async def register_user(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Basic Validation
    if password != confirm_password:
        return RedirectResponse(url="/register?error=Passwords+do+not+match", status_code=303)

    clean_email = email.strip().lower()

    # 2. Check if user already exists
    result = await db.execute(select(User).where(User.email == clean_email))
    existing_user = result.scalars().first()
    if existing_user:
        return RedirectResponse(url="/register?error=Email+already+registered", status_code=303)

    try:
        # 3. Create User and Token within a single transaction block
        new_user = User(
            name=name,
            email=clean_email,
            hashed_password=pwd_context.hash(password),
            is_verified=False
        )
        db.add(new_user)
        
        # Flush to assign an ID to new_user without committing the transaction yet
        await db.flush()

        # 4. Create the Verification Token
        token_entry = VerificationToken(user_id=new_user.id)
        db.add(token_entry)

        # Commit both the user and the token at the same time
        await db.commit()
        await db.refresh(token_entry)

        # 5. Schedule Email Sending in the background
        # This prevents the UI from "freezing" while waiting for the Resend API
        verify_url = f"{request.base_url}api/auth/verify?token={token_entry.token}"
        background_tasks.add_task(send_verification_email, name, clean_email, str(verify_url))
        
        logger.info(f"✅ User registered: {clean_email}")
        return RedirectResponse(url="/login?success=Check+your+email+to+verify+your+account", status_code=303)

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Registration process failed: {str(e)}")
        return RedirectResponse(url="/register?error=Something+went+wrong.+Please+try+again.", status_code=303)


@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    # 1. Fetch the token
    result = await db.execute(select(VerificationToken).where(VerificationToken.token == token))
    db_token = result.scalars().first()
    
    if not db_token:
        return RedirectResponse(url="/login?error=Invalid+or+expired+verification+link", status_code=303)
    
    # 2. Find the associated user
    user_result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = user_result.scalars().first()
    
    if not user:
        return RedirectResponse(url="/login?error=User+not+found", status_code=303)

    try:
        # 3. Update status and clean up token
        user.is_verified = True
        await db.delete(db_token)
        await db.commit()
        
        logger.info(f"🔓 Account verified for user: {user.email}")
        return RedirectResponse(url="/login?success=Account+verified!+You+can+now+login.", status_code=303)
    
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Verification failed: {str(e)}")
        return RedirectResponse(url="/login?error=Verification+failed+due+to+server+error", status_code=303)
