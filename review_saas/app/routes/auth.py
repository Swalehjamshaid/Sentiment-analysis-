# =====================================================
# FILE: app/routes/auth.py
# TRUSTLYTICS AI — ENTERPRISE AUTH SYSTEM
# MAY 2026 STABLE VERSION
# =====================================================

import os
import resend

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Request,
    BackgroundTasks,
    HTTPException
)

from fastapi.responses import (
    RedirectResponse
)

from sqlalchemy.ext.asyncio import (
    AsyncSession
)

from sqlalchemy.future import (
    select
)

from passlib.context import (
    CryptContext
)

from loguru import logger

# =====================================================
# INTERNAL IMPORTS
# =====================================================

from app.core.db import get_db

from app.core.models import (
    User,
    VerificationToken
)

# =====================================================
# ROUTER
# =====================================================

router = APIRouter(

    prefix="/api/auth",

    tags=["Authentication"]
)

# =====================================================
# PASSWORD HASHING
# =====================================================

pwd_context = CryptContext(

    schemes=["bcrypt"],

    deprecated="auto"
)

# =====================================================
# RESEND CONFIG
# =====================================================

resend.api_key = os.getenv(
    "RESEND_API_KEY"
)

MAIL_FROM = os.getenv(

    "MAIL_FROM",

    "onboarding@resend.dev"
)

# =====================================================
# SEND VERIFICATION EMAIL
# =====================================================

def send_verification_email(

    name: str,

    email: str,

    verify_url: str
):

    try:

        resend.Emails.send({

            "from": MAIL_FROM,

            "to": email,

            "subject":
                "Verify your Trustlytics AI Account",

            "html": f"""

                <div style="
                    font-family:sans-serif;
                    max-width:600px;
                    margin:auto;
                    border:1px solid #e5e7eb;
                    padding:20px;
                    border-radius:12px;
                ">

                    <h2 style="color:#4f46e5;">

                        Welcome to Trustlytics AI!

                    </h2>

                    <p>

                        Hi {name},

                    </p>

                    <p>

                        Please verify your account.

                    </p>

                    <div style="
                        text-align:center;
                        margin:30px 0;
                    ">

                        <a href="{verify_url}"

                           style="
                                display:inline-block;
                                background:#6366f1;
                                color:white;
                                padding:12px 24px;
                                border-radius:8px;
                                text-decoration:none;
                                font-weight:bold;
                           ">

                            Verify My Account

                        </a>

                    </div>

                    <p style="
                        margin-top:20px;
                        font-size:12px;
                        color:#6b7280;
                    ">

                        If button doesn't work,
                        copy this URL:

                        <br><br>

                        {verify_url}

                    </p>

                </div>

            """
        })

        logger.info(
            f"📧 Verification email sent to {email}"
        )

    except Exception as e:

        logger.error(
            f"❌ Email sending failed: {str(e)}"
        )

# =====================================================
# REGISTER USER
# =====================================================

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

    # =================================================
    # PASSWORD MATCH
    # =================================================

    if password != confirm_password:

        return RedirectResponse(

            url="/register?error=Passwords+do+not+match",

            status_code=303
        )

    clean_email = email.strip().lower()

    # =================================================
    # USER EXISTS
    # =================================================

    result = await db.execute(

        select(User).where(
            User.email == clean_email
        )
    )

    existing_user = result.scalars().first()

    if existing_user:

        return RedirectResponse(

            url="/register?error=Email+already+registered",

            status_code=303
        )

    try:

        # =============================================
        # CREATE USER
        # =============================================

        new_user = User(

            name=name,

            email=clean_email,

            hashed_password=
                pwd_context.hash(password),

            is_verified=False
        )

        db.add(new_user)

        await db.flush()

        # =============================================
        # CREATE TOKEN
        # =============================================

        token_entry = VerificationToken(

            user_id=new_user.id
        )

        db.add(token_entry)

        await db.commit()

        await db.refresh(token_entry)

        # =============================================
        # VERIFICATION URL
        # =============================================

        verify_url = (

            f"{request.base_url}"
            f"api/auth/verify?"
            f"token={token_entry.token}"
        )

        # =============================================
        # SEND EMAIL
        # =============================================

        background_tasks.add_task(

            send_verification_email,

            name,

            clean_email,

            str(verify_url)
        )

        logger.info(
            f"✅ User registered: {clean_email}"
        )

        return RedirectResponse(

            url="/login?success=Check+your+email+to+verify+your+account",

            status_code=303
        )

    except Exception as e:

        await db.rollback()

        logger.error(
            f"❌ Registration failed: {str(e)}"
        )

        return RedirectResponse(

            url="/register?error=Something+went+wrong",

            status_code=303
        )

# =====================================================
# VERIFY EMAIL
# =====================================================

@router.get("/verify")

async def verify_email(

    token: str,

    db: AsyncSession = Depends(get_db)

):

    result = await db.execute(

        select(VerificationToken).where(
            VerificationToken.token == token
        )
    )

    db_token = result.scalars().first()

    if not db_token:

        return RedirectResponse(

            url="/login?error=Invalid+verification+link",

            status_code=303
        )

    user_result = await db.execute(

        select(User).where(
            User.id == db_token.user_id
        )
    )

    user = user_result.scalars().first()

    if not user:

        return RedirectResponse(

            url="/login?error=User+not+found",

            status_code=303
        )

    try:

        user.is_verified = True

        await db.delete(db_token)

        await db.commit()

        logger.info(
            f"✅ Verified: {user.email}"
        )

        return RedirectResponse(

            url="/login?success=Account+verified",

            status_code=303
        )

    except Exception as e:

        await db.rollback()

        logger.error(
            f"❌ Verification failed: {str(e)}"
        )

        return RedirectResponse(

            url="/login?error=Verification+failed",

            status_code=303
        )

# =====================================================
# LOGIN USER
# =====================================================

@router.post("/login")

async def login_user(

    request: Request,

    email: str = Form(...),

    password: str = Form(...),

    db: AsyncSession = Depends(get_db)

):

    clean_email = email.strip().lower()

    # =================================================
    # FIND USER
    # =================================================

    result = await db.execute(

        select(User).where(
            User.email == clean_email
        )
    )

    user = result.scalars().first()

    # =================================================
    # USER NOT FOUND
    # =================================================

    if not user:

        return RedirectResponse(

            url="/login?error=Invalid+email+or+password",

            status_code=303
        )

    # =================================================
    # PASSWORD VERIFY
    # =================================================

    valid_password = pwd_context.verify(

        password,

        user.hashed_password
    )

    if not valid_password:

        return RedirectResponse(

            url="/login?error=Invalid+email+or+password",

            status_code=303
        )

    # =================================================
    # EMAIL VERIFIED
    # =================================================

    if not user.is_verified:

        return RedirectResponse(

            url="/login?error=Please+verify+your+email+first",

            status_code=303
        )

    # =================================================
    # SESSION
    # =================================================

    request.session["user_id"] = user.id

    request.session["user_name"] = user.name

    request.session["user_email"] = user.email

    logger.info(
        f"✅ User logged in: {user.email}"
    )

    # =================================================
    # REDIRECT
    # =================================================

    return RedirectResponse(

        url="/dashboard",

        status_code=303
    )

# =====================================================
# LOGOUT
# =====================================================

@router.get("/logout")

async def logout_user(

    request: Request
):

    request.session.clear()

    logger.info(
        "✅ User logged out"
    )

    return RedirectResponse(

        url="/login",

        status_code=303
    )
