
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from email_validator import validate_email, EmailNotValidError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import bleach
from .db import get_db
from .models import User, LoginAttempt
from .schemas import UserCreate, UserLogin
from .utils.security import verify_password, get_password_hash, create_access_token
from .config import SECRET_KEY, TOKEN_EXPIRE_EMAIL_VERIFICATION_H, TOKEN_EXPIRE_PASSWORD_RESET_MIN, LOCKOUT_MAX_ATTEMPTS, LOCKOUT_DURATION_MIN
from .services.emailer import send_email
import os

from .config import GOOGLE_OAUTH, TWOFA_ENABLED
import pyotp
from .deps import get_current_user

# 2FA: enable (TOTP) and verify
@router.post('/2fa/enable')
async def enable_2fa(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.twofa_enabled:
        return {'message': '2FA already enabled'}
    secret = pyotp.random_base32()
    current_user.twofa_secret = secret
    current_user.twofa_enabled = True
    db.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name='Reputation SaaS')
    return {'otpauth_uri': uri}

@router.post('/2fa/verify')
async def verify_2fa(code: str, current_user: User = Depends(get_current_user)):
    if not current_user.twofa_enabled or not current_user.twofa_secret:
        raise HTTPException(status_code=400, detail='2FA not enabled')
    totp = pyotp.TOTP(current_user.twofa_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail='Invalid 2FA code')
    return {'message': '2FA verified'}

# Manual unlock via email
@router.post('/unlock/request')
async def unlock_request(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==email).first()
    if not user:
        return {'message':'If the account exists, an unlock link was sent.'}
    token = serializer.dumps({'email': email}, salt='unlock')
    link = f"/auth/unlock/confirm?token={token}"
    send_email(email, 'Unlock your account', f"<p>Click to unlock: <a href='{link}'>Unlock</a></p>")
    return {'message':'If the account exists, an unlock link was sent.'}

@router.get('/unlock/confirm')
async def unlock_confirm(token: str, db: Session = Depends(get_db)):
    try:
        data = serializer.loads(token, salt='unlock', max_age=3600)
        email = data.get('email')
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid token')
    user = db.query(User).filter(User.email==email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    user.login_attempts = 0
    user.lock_until = None
    db.commit()
    return {'message':'Account unlocked'}


router = APIRouter(prefix='/auth', tags=['auth'])

serializer = URLSafeTimedSerializer(SECRET_KEY)


def _client_ip(req: Request) -> str:
    return req.client.host if req.client else 'unknown'

@router.post('/register')
async def register(req: Request, full_name: str = Form(...), email: str = Form(...), password: str = Form(...), profile_picture: UploadFile | None = File(None), db: Session = Depends(get_db)):
    try:
        v = validate_email(email)
        email = v.email
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail='Email already registered')

    # Password rules
    import re
    if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'[a-z]', password) or not re.search(r'\d', password) or not re.search(r'[^A-Za-z0-9]', password):
        raise HTTPException(status_code=400, detail='Weak password')

    # Optional profile picture
    pic_url = None
    if profile_picture:
        if profile_picture.content_type not in ('image/jpeg', 'image/png'):
            raise HTTPException(status_code=400, detail='Only JPEG/PNG allowed')
        contents = await profile_picture.read()
        if len(contents) > 2*1024*1024:
            raise HTTPException(status_code=400, detail='Max 2MB allowed')
        # Save to disk
        folder = 'uploads/profile_pics'
        os.makedirs(folder, exist_ok=True)
        filename = f"{datetime.utcnow().timestamp()}_{profile_picture.filename}"
        with open(os.path.join(folder, filename), 'wb') as f:
            f.write(contents)
        pic_url = f"/{folder}/{filename}"

    token = serializer.dumps({'email': email}, salt='email-verify')
    user = User(full_name=bleach.clean(full_name[:100], strip=True), email=email, password_hash=get_password_hash(password), profile_pic_url=pic_url, email_verification_token=token, email_verification_expires=datetime.utcnow()+timedelta(hours=TOKEN_EXPIRE_EMAIL_VERIFICATION_H))
    db.add(user); db.commit(); db.refresh(user)

    verify_link = f"/auth/verify?token={token}"
    send_email(email, 'Verify your email', f"<p>Click to verify: <a href='{verify_link}'>Verify</a></p>")
    return {'message': 'Registered. Please verify your email.'}

@router.get('/verify')
async def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        data = serializer.loads(token, salt='email-verify', max_age=TOKEN_EXPIRE_EMAIL_VERIFICATION_H*3600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Verification token expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')

    email = data.get('email')
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    user.email_verified = True
    db.commit()
    return {'message': 'Email verified'}

@router.post('/login')
async def login(req: Request, res: Response, payload: UserLogin, db: Session = Depends(get_db), code: str | None = None):
    user = db.query(User).filter(User.email == payload.email).first()
    ip = _client_ip(req)
    if not user or user.status=='suspended':
        db.add(LoginAttempt(user_id=None, ip_address=ip, success=False))
        db.commit()
        raise HTTPException(status_code=400, detail='Invalid credentials')

    # Lockout check
    if user.lock_until and user.lock_until > datetime.utcnow():
        raise HTTPException(status_code=403, detail='Account locked. Try later or check email.')

    if not verify_password(payload.password, user.password_hash):
        user.login_attempts = (user.login_attempts or 0) + 1
        if user.login_attempts >= LOCKOUT_MAX_ATTEMPTS:
            user.lock_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MIN)
        db.add(LoginAttempt(user_id=user.id, ip_address=ip, success=False))
        db.commit()
        raise HTTPException(status_code=400, detail='Invalid credentials')

    # Success
    user.login_attempts = 0
    # If 2FA enabled, require valid code before issuing token
    if user.twofa_enabled and user.twofa_secret:
        if not code:
            raise HTTPException(status_code=206, detail='2FA required')
        import pyotp
        if not pyotp.TOTP(user.twofa_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail='Invalid 2FA code')
    user.last_login_at = datetime.utcnow()
    db.add(LoginAttempt(user_id=user.id, ip_address=ip, success=True))
    db.commit()

    token = create_access_token({'sub': str(user.id)})
    res.set_cookie(key='access_token', value=token, httponly=True, secure=True, samesite='lax')
    return {'message': 'Logged in', 'user_id': user.id}

@router.post('/logout')
async def logout(res: Response):
    res.delete_cookie('access_token')
    return {'message': 'Logged out'}

# Password reset
@router.post('/password/reset/request')
async def password_reset_request(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {'message': 'If the email exists, a reset link was sent.'}
    token = serializer.dumps({'email': email}, salt='pwd-reset')
    link = f"/auth/password/reset/confirm?token={token}"
    send_email(email, 'Password Reset', f"<p>Reset your password: <a href='{link}'>Reset</a> (expires in {TOKEN_EXPIRE_PASSWORD_RESET_MIN} min)</p>")
    return {'message': 'If the email exists, a reset link was sent.'}

@router.post('/password/reset/confirm')
async def password_reset_confirm(token: str, new_password: str, db: Session = Depends(get_db)):
    import re
    if len(new_password) < 8 or not re.search(r'[A-Z]', new_password) or not re.search(r'[a-z]', new_password) or not re.search(r'\d', new_password) or not re.search(r'[^A-Za-z0-9]', new_password):
        raise HTTPException(status_code=400, detail='Weak password')
    try:
        data = serializer.loads(token, salt='pwd-reset', max_age=TOKEN_EXPIRE_PASSWORD_RESET_MIN*60)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail='Reset token expired')
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid token')

    email = data.get('email')
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    user.password_hash = get_password_hash(new_password)
    db.commit()
    return {'message': 'Password updated'}


from authlib.integrations.starlette_client import OAuth
from starlette.responses import RedirectResponse
from starlette.requests import Request as StarletteRequest

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_OAUTH['client_id'],
    client_secret=GOOGLE_OAUTH['client_secret'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@router.get('/oauth/google/login')
async def google_login(request: StarletteRequest):
    redirect_uri = GOOGLE_OAUTH['redirect_uri']
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get('/oauth/google/callback')
async def google_callback(request: StarletteRequest, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo')
    if not userinfo:
        from authlib.oidc.core import UserInfo
        userinfo = await oauth.google.parse_id_token(request, token)
    email = userinfo.get('email')
    sub = userinfo.get('sub')
    name = userinfo.get('name')
    user = db.query(User).filter(User.email==email).first()
    if not user:
        user = User(full_name=name[:100] if name else 'Google User', email=email, password_hash=get_password_hash('oauth-'+sub), email_verified=True, oauth_provider='google', oauth_sub=sub)
        db.add(user); db.commit(); db.refresh(user)
    res = RedirectResponse('/')
    jwt_token = create_access_token({'sub': str(user.id)})
    res.set_cookie(key='access_token', value=jwt_token, httponly=True, secure=True, samesite='lax')
    return res
