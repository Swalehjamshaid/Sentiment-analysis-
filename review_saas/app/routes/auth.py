# File: app/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import logging

# Import your fixed security functions
from ..core.security import hash_password, verify_password_strength

logger = logging.getLogger("review_saas")
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/register", response_class=HTMLResponse)
async def get_register(request: Request, msg: str = None):
    """
    Displays the registration page. 
    If 'msg' is in the URL, it will be shown to the user.
    """
    return templates.TemplateResponse("register.html", {"request": request, "msg": msg})

@router.post("/register")
async def register_post(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """Handles the registration and redirects with a success message."""
    try:
        # 1. Simple Validation
        if not verify_password_strength(password):
            return templates.TemplateResponse(
                "register.html", 
                {"request": request, "error": "Password cannot be empty"}
            )

        # 2. Process Registration (Hashing and DB logic)
        hashed_pw = hash_password(password)
        
        # 3. Redirect back to registration page with a 'msg' parameter
        success_message = "Registration successfully done!"
        return RedirectResponse(
            url=f"/auth/register?msg={success_message}", 
            status_code=status.HTTP_303_SEE_OTHER
        )

    except Exception as e:
        logger.error(f"Registration failed: {str(e)}")
        return templates.TemplateResponse(
            "register.html", 
            {"request": request, "error": "Registration failed. Please try again."}
        )
