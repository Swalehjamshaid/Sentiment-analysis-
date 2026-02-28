# File: app/routes/auth.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging

# Use an empty prefix to ensure routes like /register are top-level
router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("review_saas")

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Renders the registration page."""
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
async def register_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """Handles user registration logic."""
    try:
        # Registration logic (database insertion, etc.) goes here
        logger.info(f"New registration attempt for: {email}")
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "msg": "Registration successful! Please login."
        })
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "An error occurred during registration."
        })

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Renders the login page."""
    return templates.TemplateResponse("login.html", {"request": request})
