# FILE: app/routes/auth.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["Auth"])

@router.post("/auth/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    # ⚠️ Demo only. Replace with real verification + password hashing.
    request.session["user"] = {"id": 1, "email": email, "full_name": "Demo User", "role": "owner"}
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")
