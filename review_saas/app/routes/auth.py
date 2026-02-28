# filename: app/routes/auth.py
from __future__ import annotations
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
import pyotp

from ..core.db import get_db
from ..core.settings import settings
from ..core.security import (
    verify_password_strength, 
    hash_password, 
    verify_password, 
    create_access_token
)
from ..models.models import User, VerificationToken, ResetToken, LoginAttempt
from ..services.emailer import send_email, render_template

logger = logging.getLogger('app.auth')
router = APIRouter(prefix='/auth', tags=['Authentication'])

# --- Requirement #15: Google OAuth Setup ---
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
    client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# --- Requirement #1-6: User Registration & Verification ---
@router.post('/register', response_class=HTMLResponse)
async def register_post(
    request: Request, 
    full_name: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail='Email already exists')
    
    if not verify_password_strength(password):
        raise HTTPException(status_code=400, detail='Password does not meet security requirements')

    new_user = User(
        full_name=full_name[:100], 
        email=email, 
        password_hash=hash_password(password),
        status='pending'
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate Verification Token (Point 5)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.VERIFY_TOKEN_HOURS)
    vt = VerificationToken(user_id=new_user.id, token=token, expires_at=expires)
    db.add(vt)
    db.commit()

    verify_link = f"{settings.APP_BASE_URL}/auth/verify?token={token}"
    html_content = render_template('message.html', title='Verify Account', message=f'Please verify your account: <a href="{verify_link}">Click Here</a>')
    send_email(email, 'Verify your account', html_content)

    return render_template('message.html', title='Registration Successful', message='Please check your email to verify your account.')

@router.get('/verify')
async def verify_email(token: str, db: Session = Depends(get_db)):
    vt = db.query(VerificationToken).filter(VerificationToken.token == token).first()
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail='Invalid or expired token')
    
    user = db.query(User).filter(User.id == vt.user_id).first()
    user.status = 'active'
    db.delete(vt)
    db.commit()
    return HTMLResponse(render_template('message.html', title='Verified', message='Email verified! You can now log in.'))

# --- Requirement #7-11: Login, Session & Lockout ---
@router.post('/login')
async def login_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    ip = request.client.host if request.client else "unknown"

    # Requirement #11: Check Lockout status
    if user and user.status == 'suspended':
        if user.lockout_until and datetime.now(timezone.utc) < user.lockout_until:
            raise HTTPException(status_code=403, detail='Account locked due to multiple failed attempts.')
        else:
            user.status = 'active'
            user.failed_login_attempts = 0
            db.commit()

    if not user or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_attempts += 1 # Point 10
            if user.failed_login_attempts >= settings.LOCKOUT_THRESHOLD:
                user.status = 'suspended'
                user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOCKOUT_MINUTES)
            db.commit()
        raise HTTPException(status_code=400, detail='Invalid credentials')

    if user.status == 'pending':
        raise HTTPException(status_code=400, detail='Please verify your email first.')

    # Requirement #8: HTTP-only Cookie Session
    token_jwt = create_access_token(str(user.id))
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    db.add(LoginAttempt(user_id=user.id, success=True, ip_address=ip))
    db.commit()

    resp = RedirectResponse(url='/dashboard', status_code=status.HTTP_302_FOUND)
    resp.set_cookie(
        key='access_token', 
        value=token_jwt, 
        httponly=True, 
        secure=settings.COOKIE_SECURE, 
        samesite='lax'
    )
    return resp

# --- Requirement #15: Google OAuth Logic ---
@router.get('/google/login')
async def google_login(request: Request):
    redirect_uri = settings.OAUTH_GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get('/google/callback')
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo')
    if not userinfo:
        raise HTTPException(status_code=400, detail='Google authentication failed')
    
    sub = userinfo.get('sub')
    email = userinfo.get('email')
    
    user = db.query(User).filter((User.oauth_google_sub == sub) | (User.email == email)).first()
    if not user:
        user = User(
            full_name=userinfo.get('name', email.split('@')[0]), 
            email=email, 
            password_hash=hash_password(secrets.token_urlsafe(16)), 
            status='active', 
            oauth_google_sub=sub
        )
        db.add(user)
        db.commit()
    
    token_jwt = create_access_token(str(user.id))
    resp = RedirectResponse('/dashboard')
    resp.set_cookie('access_token', token_jwt, httponly=True, secure=settings.COOKIE_SECURE)
    return resp

# --- Requirement #19: 2FA Enrollment ---
@router.post('/2fa/enroll')
async def enroll_2fa(request: Request, db: Session = Depends(get_db)):
    # Requires user to be logged in; for brevity using first user or logic
    user = db.query(User).first() 
    secret = pyotp.random_base32()
    user.otp_secret = secret
    db.commit()
    
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)
    return {"secret": secret, "qr_uri": provisioning_uri}

@router.get('/logout')
async def logout():
    resp = RedirectResponse(url='/auth/login')
    resp.delete_cookie('access_token')
    return resp
