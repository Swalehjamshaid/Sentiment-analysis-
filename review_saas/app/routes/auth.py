# FILE: app/routes/auth.py

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User  # Ensure you import your User model

router = APIRouter(tags=["Auth"])

# ─────────────────────────────────────────────────────────────
# NEW: Registration Route (Fixes the 404 error)
# ─────────────────────────────────────────────────────────────
@router.post("/register")
async def register_post(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        request.session["flash_error"] = "Email already registered."
        return RedirectResponse(url="/login", status_code=303)

    # Create new user
    # NOTE: In production, use passlib to hash this password!
    new_user = User(
        full_name=full_name, 
        email=email, 
        password_hash=password, 
        status="active"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Set session with the REAL database ID
    request.session["user"] = {
        "id": new_user.id,
        "email": new_user.email,
        "full_name": new_user.full_name,
        "role": "owner"
    }
    return RedirectResponse(url="/dashboard", status_code=303)

# ─────────────────────────────────────────────────────────────
# UPDATED: Login Route (Fixes the 500 error)
# ─────────────────────────────────────────────────────────────
@router.post("/login")
async def login_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Search for user in database
    user = db.query(User).filter(User.email == email).first()
    
    # Verify password (Simple string check for now)
    if not user or user.password_hash != password:
        request.session["flash_error"] = "Invalid email or password."
        return RedirectResponse(url="/login", status_code=303)
    
    # Use real user data from the DB
    request.session["user"] = {
        "id": user.id, 
        "email": user.email, 
        "full_name": user.full_name, 
        "role": "owner"
    }
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
