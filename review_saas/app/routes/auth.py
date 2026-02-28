# filename: app/routes/auth.py
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth

from ..core.db import get_db
from ..core.settings import settings
from ..core.security import verify_password_strength, hash_password, verify_password, create_access_token
from ..models.models import User, VerificationToken, ResetToken, LoginAttempt
from ..services.emailer import send_email, render_template

# Defining router without a prefix to allow root-level /login
router = APIRouter(tags=['Authentication'])
templates = Jinja2Templates(directory='app/templates')

# Google OAuth Setup (Requirement #15)
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
    client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@router.get('/login', response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse('login.html', {'request': request})

@router.post('/login')
async def login_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    ip = request.client.host if request.client else "0.0.0.0"

    # Requirement #10-11: Lockout Logic
    if user and user.status == 'suspended':
        if user.lockout_until and datetime.now(timezone.utc) < user.lockout_until:
            return templates.TemplateResponse('login.html', {
                'request': request, 'error': 'Account locked. Try again later.'
            })
    
    if not user or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.LOCKOUT_THRESHOLD:
                user.status = 'suspended'
                user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOCKOUT_MINUTES)
            db.commit()
        return templates.TemplateResponse('login.html', {'request': request, 'error': 'Invalid credentials'})

    # Requirement #8: Session via HTTP-only Cookie
    token = create_access_token(str(user.id))
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    db.add(LoginAttempt(user_id=user.id, success=True, ip_address=ip))
    db.commit()

    response = RedirectResponse(url='/dashboard', status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key='access_token', 
        value=token, 
        httponly=True, 
        secure=settings.COOKIE_SECURE, 
        samesite='lax'
    )
    return response

@router.get('/register', response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse('register.html', {'request': request})

@router.post('/register')
async def register_post(
    request: Request, 
    full_name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Email exists'})
    
    if not verify_password_strength(password):
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Password too weak'})

    user = User(full_name=full_name, email=email, password_hash=hash_password(password), status='pending')
    db.add(user); db.commit(); db.refresh(user)

    # Requirement #5: Verification
    token = secrets.token_urlsafe(32)
    vt = VerificationToken(user_id=user.id, token=token, expires_at=datetime.now(timezone.utc)+timedelta(hours=24))
    db.add(vt); db.commit()

    verify_link = f"{settings.APP_BASE_URL}/verify?token={token}"
    send_email(email, 'Verify Account', f"Link: {verify_link}")

    return templates.TemplateResponse('message.html', {'request': request, 'message': 'Check email to verify'})

@router.get('/logout')
async def logout():
    response = RedirectResponse(url='/login')
    response.delete_cookie('access_token')
    return response
