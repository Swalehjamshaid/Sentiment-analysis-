# filename: app/routes/auth.py
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth, OAuthError

from ..core.db import get_db
from ..core.settings import settings
from ..core.security import verify_password_strength, hash_password, verify_password, create_access_token
from ..models.models import User, VerificationToken, LoginAttempt
from ..services.emailer import send_email

# Router without prefix to keep /login and /register at the root level
router = APIRouter(tags=['Authentication'])
templates = Jinja2Templates(directory='app/templates')

# Google OAuth Setup
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
    client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# --- LOGIN FLOW ---

@router.get('/login', response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse('login.html', {'request': request})

@router.post('/auth/token')
async def login_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    ip = request.client.host if request.client else "0.0.0.0"

    # Lockout check
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

    # Success: Set Cookie
    token = create_access_token(str(user.id))
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    db.add(LoginAttempt(user_id=user.id, success=True, ip_address=ip))
    db.commit()

    response = RedirectResponse(url='/dashboard', status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key='access_token', value=token, httponly=True, 
        secure=settings.COOKIE_SECURE, samesite='lax'
    )
    return response

# --- GOOGLE OAUTH FLOW ---

@router.get('/auth/google/login')
async def google_login(request: Request):
    redirect_uri = f"{settings.APP_BASE_URL}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get('/auth/google/callback')
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        return templates.TemplateResponse('login.html', {'request': request, 'error': f'Google Auth Failed: {error.error}'})
    
    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to fetch user info")

    user = db.query(User).filter(User.email == user_info['email']).first()
    if not user:
        user = User(
            full_name=user_info.get('name', 'Google User'),
            email=user_info['email'],
            password_hash="OAUTH_USER",
            status='active'
        )
        db.add(user); db.commit(); db.refresh(user)

    access_token = create_access_token(str(user.id))
    response = RedirectResponse(url='/dashboard')
    response.set_cookie(key='access_token', value=access_token, httponly=True, samesite='lax')
    return response

# --- REGISTRATION FLOW ---

@router.get('/register', response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse('register.html', {'request': request})

@router.post('/auth/register')
async def register_post(
    request: Request, 
    full_name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Email already exists'})
    
    if not verify_password_strength(password):
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Password too weak'})

    user = User(full_name=full_name, email=email, password_hash=hash_password(password), status='pending')
    db.add(user); db.commit(); db.refresh(user)

    # Verification Email
    token = secrets.token_urlsafe(32)
    vt = VerificationToken(user_id=user.id, token=token, expires_at=datetime.now(timezone.utc)+timedelta(hours=24))
    db.add(vt); db.commit()

    verify_link = f"{settings.APP_BASE_URL}/auth/verify?token={token}"
    send_email(email, 'Verify Your Account', f"Click here to verify: {verify_link}")

    return templates.TemplateResponse('message.html', {
        'request': request, 
        'title': 'Registration Successful', 
        'message': 'Please check your email to verify your account.'
    })

@router.get('/auth/verify')
async def verify_email(token: str, db: Session = Depends(get_db)):
    vt = db.query(VerificationToken).filter(VerificationToken.token == token).first()
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    user = db.query(User).get(vt.user_id)
    user.status = 'active'
    db.delete(vt); db.commit()
    return RedirectResponse(url='/login?verified=true')

@router.get('/logout')
async def logout():
    response = RedirectResponse(url='/login')
    response.delete_cookie('access_token')
    return response
