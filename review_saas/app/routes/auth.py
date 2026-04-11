from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core.models import User
from app.core.security import get_password_hash, create_verification_token, decode_verification_token
from app.core.mailer import send_verification_email

# Define the router to match the prefix in main.py
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    """
    1. Validates form data (Form(...))
    2. Creates unverified user in Database
    3. Generates JWT Magic Token
    4. Sends Email via Resend API
    """
    # 1. Check for duplicate email
    result = await db.execute(select(User).where(User.email == email.strip().lower()))
    if result.scalars().first():
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "This email is already registered."
        })

    # 2. Create the user object
    new_user = User(
        name=name,
        email=email.strip().lower(),
        hashed_password=get_password_hash(password),
        email_verified=False,
        is_active=True
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # 3. Create the Magic Link Token
    token = create_verification_token(new_user.email)
    
    # 4. Fire the email via Resend
    try:
        await send_verification_email(new_user.email, token)
    except Exception as e:
        # If email fails, we log it but the user is already in the DB
        print(f"RESEND ERROR: {str(e)}")
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "Account created, but verification email failed. Please contact support."
        })

    return templates.TemplateResponse("register.html", {
        "request": request, 
        "success": "Registration successful! Check your inbox for your Magic Login Link."
    })


@router.get("/verify")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    """
    Handles the click from the user's email.
    Verifies the token, activates the user, and auto-logs them in.
    """
    # 1. Decode the JWT
    email = decode_verification_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link.")

    # 2. Find user in DB
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 3. Mark as verified
    if not user.email_verified:
        user.email_verified = True
        await db.commit()

    # 4. AUTO-LOGIN: Set the session cookie and go to dashboard
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_user", 
        value=user.email, 
        httponly=True, 
        max_age=86400, # 24 hours
        samesite="lax",
        secure=True
    )
    # Also set the session for your main.py middleware
    request_session = {"id": user.id, "email": user.email, "name": user.name}
    
    return response
