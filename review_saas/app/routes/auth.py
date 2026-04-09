# filename: app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.core.db import get_db
from app.core.models import User
# Ensure these imports match your security logic
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
            # Redirect back to register with an error if you have a register route
            # For now, we raise an exception which the global handler in main.py will catch
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Email is already registered."
            )

        # 2. Create new user instance
        # email_verified set to True for now to bypass verification for testing
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
        
        logger.info(f"✅ New user registered: {email_clean}")

        # 4. Redirect to login page with a success flag
        return RedirectResponse(url="/login?msg=registered", status_code=status.HTTP_303_SEE_OTHER)

    except HTTPException as he:
        raise he
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Registration Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to a server error."
        )

# Optional: Keep the verify route if you plan to use email verification later
@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    # Logic for email verification would go here
    return {"message": "Verification logic pending mailer setup"}
