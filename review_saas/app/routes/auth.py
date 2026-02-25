# FILE: app/routes/auth.py

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db

router = APIRouter(tags=["Auth"])

# Changed function name to 'login_post' to match main.py
# Changed route to '/login' to match the form action
@router.post("/login")
async def login_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # ⚠️ Demo logic: Replace with password hashing and DB verification
    # Example DB check: user = db.query(User).filter(User.email == email).first()
    
    request.session["user"] = {
        "id": 1, 
        "email": email, 
        "full_name": "Demo User", 
        "role": "owner"
    }
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
