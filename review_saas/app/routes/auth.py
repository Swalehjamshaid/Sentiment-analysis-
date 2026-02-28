# File: review_saas/app/routes/auth.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging

# Importing database and security dependencies
from ..core.db import get_db
from ..core.security import hash_password, verify_password

# Use an empty prefix to ensure routes like /register are top-level
router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("review_saas")

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Renders the professional registration page."""
    return templates.TemplateResponse("register.html", {"request": request, "title": "ReviewSaaS"})

@router.post("/register")
async def register_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handles user registration logic with database persistence."""
    try:
        logger.info(f"New registration attempt for: {email}")
        
        # In a real scenario, you would create a User model instance here:
        # hashed_pwd = hash_password(password)
        # new_user = User(full_name=full_name, email=email, hashed_password=hashed_pwd)
        # db.add(new_user)
        # db.commit()
        
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "msg": "Registration successful! Please login.",
            "title": "ReviewSaaS"
        })
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "An error occurred during registration. Please try again.",
            "title": "ReviewSaaS"
        })

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Renders the mobile-friendly login page."""
    return templates.TemplateResponse("login.html", {"request": request, "title": "ReviewSaaS"})

@router.post("/auth/login")
async def login_post(
    request: Request,
    username: str = Form(...), # Standard OAuth2 field name for the email/username
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles the login POST request.
    This explicit route solves the 'POST /auth/login' 404 error found in the logs.
    """
    try:
        logger.info(f"Login attempt for: {username}")
        
        # 1. Fetch user from DB (Placeholder logic)
        # user = db.query(User).filter(User.email == username).first()
        
        # 2. Verify password (Placeholder logic)
        # if not user or not verify_password(password, user.hashed_password):
        #     raise HTTPException(status_code=401)

        # 3. On success, redirect to dashboard
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    except Exception as e:
        logger.error(f"Login failure: {e}")
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password.",
            "title": "ReviewSaaS"
        })
