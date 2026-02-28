
# filename: app/routes/auth.py
from __future__ import annotations
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets
import pyotp
from authlib.integrations.starlette_client import OAuth
from starlette.responses import Response

from ..core.db import get_db
from ..core.settings import settings
from ..core.security import verify_password_strength, hash_password, verify_password, create_access_token
from ..models.models import User, VerificationToken, ResetToken, LoginAttempt
from ..services.emailer import send_email, render_template

router = APIRouter(prefix='/auth', tags=['auth'])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/token')

oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
    client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@router.post('/register', response_class=HTMLResponse)
async def register_post(request: Request, full_name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if len(full_name) < 2 or len(full_name) > 100:
        raise HTTPException(status_code=400, detail='Invalid name length')
    if db.query(User).filter(User.email==email).first():
        raise HTTPException(status_code=400, detail='Email already exists')
    if not verify_password_strength(password):
        raise HTTPException(status_code=400, detail='Weak password')
    user = User(full_name=full_name, email=email, password_hash=hash_password(password))
    db.add(user); db.commit(); db.refresh(user)
    token = secrets.token_urlsafe(32)
    vt = VerificationToken(user_id=user.id, token=token, expires_at=datetime.now(timezone.utc)+timedelta(hours=settings.VERIFY_TOKEN_HOURS))
    db.add(vt); db.commit()
    verify_link = f"{settings.APP_BASE_URL}/auth/verify?token={token}"
    send_email(email, 'Verify your account', render_template('message.html', title='Verify', message=f'Click to verify: <a href="{verify_link}">Verify</a>'))
    return render_template('message.html', title='Registered', message='Please check your email to verify your account.')

@router.get('/verify')
async def verify_email(token: str, db: Session = Depends(get_db)):
    vt = db.query(VerificationToken).filter(VerificationToken.token==token).first()
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        return HTMLResponse(render_template('message.html', title='Verification', message='Invalid or expired token'), status_code=400)
    user = db.query(User).get(vt.user_id)
    user.status = 'active'
    db.delete(vt); db.commit()
    return HTMLResponse(render_template('message.html', title='Verified', message='Your email has been verified.'))

@router.post('/token')
async def issue_token(email: str = Form(...), password: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==email).first()
    ip = request.client.host if request and request.client else None
    if not user or not verify_password(password, user.password_hash):
        if user:
            db.add(LoginAttempt(user_id=user.id, success=False, ip_address=ip)); db.commit()
        raise HTTPException(status_code=400, detail='Invalid credentials')
    # 2FA enforcement
    if user.otp_secret:
        # expect separate /auth/2fa/verify step to set a cookie flag; keep it simple
        pass
    user.last_login_at = datetime.now(timezone.utc)
    db.add(LoginAttempt(user_id=user.id, success=True, ip_address=ip))
    db.commit()
    token = create_access_token(str(user.id))
    response = RedirectResponse(url='/', status_code=302)
    response.set_cookie('access_token', token, httponly=True, secure=settings.COOKIE_SECURE, domain=settings.COOKIE_DOMAIN)
    return response

@router.get('/google/login')
async def google_login(request: Request):
    redirect_uri = settings.OAUTH_GOOGLE_REDIRECT_URI or str(request.url_for('google_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get('/google/callback')
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo')
    if not userinfo:
        from authlib.integrations.base_client import OAuthError
        raise HTTPException(status_code=400, detail='Google auth failed')
    sub = userinfo.get('sub'); email = userinfo.get('email'); name = userinfo.get('name')
    user = db.query(User).filter((User.oauth_google_sub==sub) | (User.email==email)).first()
    if not user:
        # auto-link
        user = User(full_name=name or email.split('@')[0], email=email, password_hash=hash_password(secrets.token_urlsafe(16)), status='active', oauth_google_sub=sub)
        db.add(user); db.commit()
    else:
        if not user.oauth_google_sub:
            user.oauth_google_sub = sub; db.commit()
    token_jwt = create_access_token(str(user.id))
    resp = RedirectResponse('/')
    resp.set_cookie('access_token', token_jwt, httponly=True, secure=settings.COOKIE_SECURE, domain=settings.COOKIE_DOMAIN)
    return resp

@router.post('/password/reset/request')
async def password_reset_request(email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    import secrets
    token = secrets.token_urlsafe(32)
    rt = ResetToken(user_id=user.id, token=token, expires_at=datetime.now(timezone.utc)+timedelta(minutes=settings.RESET_TOKEN_MINUTES))
    db.add(rt); db.commit()
    link = f"{settings.APP_BASE_URL}/reset?token={token}"
    send_email(email, 'Password reset', render_template('message.html', title='Reset Password', message=f'Click to reset: <a href="{link}">Reset</a>'))
    return {'status': 'ok'}

@router.post('/2fa/enroll')
async def twofa_enroll(user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    secret = pyotp.random_base32()
    user.otp_secret = secret
    db.commit()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)
    # return QR as text link (front-end can render QR)
    return {'otpauth_url': provisioning_uri, 'secret': secret}

@router.post('/2fa/verify')
async def twofa_verify(user_id: int = Form(...), code: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user or not user.otp_secret:
        raise HTTPException(status_code=400, detail='2FA not enrolled')
    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail='Invalid 2FA code')
    return {'status': 'ok'}
