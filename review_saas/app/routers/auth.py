# filename: app/routes/auth.py

from fastapi import APIRouter, Request, Depends, Form, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets

from ..core.config import settings
from ..security.utils import verify_password_strength, hash_password, verify_password, create_access_token
from ..models import User, VerificationToken, LoginAttempt
from ..db import SessionLocal
from ..emailer import send_email

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

# ------------------------
# DB Dependency
# ------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------
# GET REGISTER PAGE
# ------------------------
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# ------------------------
# POST REGISTER
# ------------------------
@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_pic: UploadFile | None = None,
    db: Session = Depends(get_db)
):
    # validate email & password
    try:
        email = validate_email(email).email
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not verify_password_strength(password):
        raise HTTPException(status_code=400, detail="Weak password")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    # save profile pic
    pic_url = None
    if profile_pic and profile_pic.filename:
        data = await profile_pic.read()
        path = f"app/static/{secrets.token_hex(8)}_{profile_pic.filename}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        pic_url = "/" + path

    # create user
    user = User(full_name=full_name[:100], email=email, password_hash=hash_password(password), profile_pic_url=pic_url, status="inactive")
    db.add(user); db.commit(); db.refresh(user)

    # create verification token
    token = secrets.token_urlsafe(32)
    vt = VerificationToken(user_id=user.id, token=token, expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.VERIFY_TOKEN_HOURS))
    db.add(vt); db.commit()

    verify_link = f"{settings.APP_BASE_URL}/auth/verify?token={token}"
    send_email(user.email, "Verify your ReviewSaaS account", f"<p>Hello {user.full_name},</p><p>Verify: <a href='{verify_link}'>Activate</a></p>")

    return templates.TemplateResponse("message.html", {"request": request, "message": "Registration successful. Please verify your email."})

# ------------------------
# GET LOGIN PAGE
# ------------------------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# ------------------------
# POST LOGIN
# ------------------------
@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Email not verified")

    token = create_access_token(str(user.id))
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True, secure=False, samesite="lax")
    return response

# ------------------------
# VERIFY EMAIL
# ------------------------
@router.get("/verify", response_class=HTMLResponse)
async def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    vt = db.query(VerificationToken).filter(VerificationToken.token == token).first()
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse("verify.html", {"request": request, "message": "Invalid or expired token."})
    user = db.query(User).get(vt.user_id)
    user.status = "active"
    db.delete(vt); db.commit()
    return templates.TemplateResponse("verify.html", {"request": request, "message": "Email verified. You can now login."})
