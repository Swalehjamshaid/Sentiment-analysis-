# filename: app/routers/auth.py
from fastapi import APIRouter, Request, Depends, Form, UploadFile, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets
import pyotp

from ..core.config import settings
from ..security.utils import verify_password_strength, hash_password, verify_password, create_access_token
from ..models import Base, User, VerificationToken, ResetToken, LoginAttempt
from ..db import SessionLocal
from ..emailer import send_email

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

# Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/register', response_class=HTMLResponse)
async def register(request: Request, full_name: str = Form(...), email: str = Form(...), password: str = Form(...), profile_pic: UploadFile | None = None, db: Session = Depends(get_db)):
    try:
        v = validate_email(email)
        email = v.email
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not verify_password_strength(password):
        raise HTTPException(status_code=400, detail="Weak password")
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    pic_url = None
    if profile_pic and profile_pic.filename:
        if profile_pic.content_type not in ("image/png", "image/jpeg"):
            raise HTTPException(status_code=400, detail="Invalid image type")
        data = await profile_pic.read()
        if len(data) > 2*1024*1024:
            raise HTTPException(status_code=400, detail="Image too large")
        # NOTE: save locally; in prod use S3 or similar
        path = f"app/static/{secrets.token_hex(8)}_{profile_pic.filename}"
        with open(path, 'wb') as f:
            f.write(data)
        pic_url = "/" + path

    user = User(full_name=full_name[:100], email=email, password_hash=hash_password(password), profile_pic_url=pic_url)
    db.add(user)
    db.commit(); db.refresh(user)

    token = secrets.token_urlsafe(32)
    vt = VerificationToken(user_id=user.id, token=token, expires_at=datetime.now(timezone.utc)+timedelta(hours=settings.VERIFY_TOKEN_HOURS))
    db.add(vt); db.commit()

    verify_link = f"{settings.APP_BASE_URL}/auth/verify?token={token}"
    send_email(user.email, "Verify your ReviewSaaS account", f"<p>Hello {user.full_name},</p><p>Verify: <a href='{verify_link}'>Activate</a></p>")

    return templates.TemplateResponse('message.html', {"request": request, "message": "Registration successful. Please verify your email."})

@router.get('/verify', response_class=HTMLResponse)
async def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    vt = db.query(VerificationToken).filter(VerificationToken.token==token).first()
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse('verify.html', {"request": request, "message": "Invalid or expired token."})
    user = db.query(User).get(vt.user_id)
    user.status = 'active'
    db.delete(vt)
    db.commit()
    return templates.TemplateResponse('verify.html', {"request": request, "message": "Email verified. You can now login."})

@router.post('/login')
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==email).first()
    ip = request.client.host if request.client else None
    if not user:
        db.add(LoginAttempt(user_id=0, success=False, ip_address=ip)); db.commit()
        raise HTTPException(status_code=400, detail="Invalid credentials")
    # Lockout check
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.LOCKOUT_MINUTES)
    failed = db.query(LoginAttempt).filter(LoginAttempt.user_id==user.id, LoginAttempt.success==False, LoginAttempt.created_at>=cutoff).count()
    if failed >= settings.LOCKOUT_THRESHOLD:
        raise HTTPException(status_code=403, detail="Account locked. Try later.")

    if not verify_password(password, user.password_hash):
        db.add(LoginAttempt(user_id=user.id, success=False, ip_address=ip)); db.commit()
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if user.status != 'active':
        raise HTTPException(status_code=403, detail="Email not verified")

    # 2FA check (if enrolled)
    if user.twofa_secret:
        # Store pre-auth mark and redirect to /auth/2fa/verify (for API you'd return a code)
        request.session['pending_user_id'] = user.id if hasattr(request, 'session') else None
        return RedirectResponse(url="/twofa", status_code=302)

    db.add(LoginAttempt(user_id=user.id, success=True, ip_address=ip)); db.commit()
    token = create_access_token(str(user.id))
    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, secure=True, samesite="lax")
    return resp
