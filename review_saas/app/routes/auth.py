# filename: app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

# CORE IMPORTS
from app.core.db import get_db
from app.core.models import User
from app.core.security import get_password_hash 

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register")
async def register_user(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Handles User Registration.
    Aligned with main.py to use Form data for standard HTML form submissions.
    """
    email_clean = email.strip().lower()
    
    try:
        # 1. Check if user already exists
        result = await db.execute(select(User).where(User.email == email_clean))
        existing_user = result.scalars().first()
        
        if existing_user:
            logger.warning(f"⚠️ Registration attempt for existing email: {email_clean}")
            # Raising HTTPException allows the global_exception_handler in main.py to catch it
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Email is already registered."
            )

        # 2. Create new user instance
        # email_verified set to True to allow immediate login after registration
        new_user = User(
            name=name,
            email=email_clean,
            hashed_password=get_password_hash(password),
            email_verified=True, 
            is_active=True
        )
        
        db.add(new_user)
        
        # 3. Commit to Database
        await db.commit()
        await db.refresh(new_user)
        
        logger.info(f"✅ New user registered successfully: {email_clean}")

        # 4. Redirect to login page (303 is essential for POST -> GET redirection)
        return RedirectResponse(
            url="/login?msg=registered", 
            status_code=status.HTTP_303_SEE_OTHER
        )

    except HTTPException as he:
        # Re-raise to let FastAPI handles the known error
        raise he
    except Exception as e:
        # Rollback in case of DB errors
        await db.rollback()
        logger.error(f"❌ Registration Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to a server error."
        )

@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """Placeholder for future email verification logic."""
    return {"message": "Verification logic pending mailer setup"}
