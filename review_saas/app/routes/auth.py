# File: review_saas/app/routes/auth.py
from __future__ import annotations
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import select
import os
from app.core.config import settings
from app.core.db import get_session
from app.core.models import User, AuditLog
from app.core.security import hash_password, verify_password, validate_password_strength, create_access_token
from app.core.mailer import send_email
from app.core.rate_limit import check_rate_limit

router = APIRouter(tags=['auth'])

templates = Jinja2Templates(directory='app/templates')

s = URLSafeTimedSerializer(settings.SECRET_KEY)

# -------------------------------
# REGISTER
# -------------------------------
@router.get('/register', response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse('register.html', {"request": request, "title": "Register"})

@router.post('/register')
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_pic: UploadFile | None = File(None)
):
    # Rate limit check
    check_rate_limit(request, f"reg:{request.client.host}")

    # Validate password strength
    if not validate_password_strength(password):
        raise HTTPException(status_code=400, detail='Weak password: must contain upper, lower, number, special char, min 8 chars')

    # Handle profile picture upload
    pic_path = None
    if profile_pic and profile_pic.filename:
        upload_dir = 'app/static/uploads'
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = email.replace('@', '_at_') + '_' + profile_pic.filename
        dest = os.path.join(upload_dir, safe_name)
        with open(dest, 'wb') as w:
            w.write(await profile_pic.read())
        pic_path = '/static/uploads/' + safe_name

    async with get_session() as session:
        # Check if user already exists
        exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=400, detail='Email already registered')

        # Create new user
        u = User(
            name=name,
            email=email,
            hashed_password=hash_password(password),
            profile_pic=pic_path,
            role='editor',
            email_verified=False  # must verify email
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)

        # Audit log
        session.add(AuditLog(user_id=u.id, action='register', meta={'email': email}))
        await session.commit()

    # Send verification email
    token = s.dumps({"email": email})
    verify_link = f"/verify-email?token={token}"
    send_email(
        email,
        'Verify your email',
        f'<p>Welcome {name}! Click to verify your email: <a href="{verify_link}">{verify_link}</a></p>'
    )

    if settings.DEBUG:
        print('DEV verify link:', verify_link)

    return templates.TemplateResponse(
        'verify_sent.html',
        {"request": request, "title": "Verify Email", "verify_link": verify_link}
    )

# -------------------------------
# VERIFY EMAIL
# -------------------------------
@router.get('/verify-email', response_class=HTMLResponse)
async def verify_email(request: Request, token: str):
    try:
        data = s.loads(token, max_age=60 * 60 * 24)  # 24 hours expiry
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid or expired token')

    email = data.get('email')
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        user.email_verified = True
        session.add(AuditLog(user_id=user.id, action='verify_email', meta={'email': email}))
        await session.commit()

    return templates.TemplateResponse('verified.html', {"request": request, "title": "Email Verified"})

# -------------------------------
# LOGIN
# -------------------------------
@router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse('login.html', {"request": request, "title": "Login"})

@router.post('/login')
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    check_rate_limit(request, f"login:{request.client.host}")

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=401, detail='Invalid email or password')

        if not user.email_verified:
            raise HTTPException(status_code=401, detail='Please verify your email first')

        if not user.is_active:
            raise HTTPException(status_code=401, detail='Account is inactive')

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail='Invalid email or password')

        # Successful login
        request.session['user_id'] = user.id
        request.session['role'] = user.role

        token = create_access_token(str(user.id), extra={"role": user.role})

        session.add(AuditLog(user_id=user.id, action='login', meta={'email': email}))
        await session.commit()

    resp = RedirectResponse(url='/dashboard', status_code=302)
    resp.set_cookie('access_token', token, httponly=True, samesite='lax', secure=not settings.DEBUG)
    return resp

# -------------------------------
# LOGOUT
# -------------------------------
@router.get('/logout')
async def logout(request: Request):
    uid = request.session.get('user_id')
    if uid:
        async with get_session() as session:
            session.add(AuditLog(user_id=uid, action='logout', meta={}))
            await session.commit()

    request.session.clear()
    resp = RedirectResponse(url='/', status_code=302)
    resp.delete_cookie('access_token')
    return resp

# -------------------------------
# FORGOT PASSWORD
# -------------------------------
@router.get('/forgot', response_class=HTMLResponse)
async def forgot_page(request: Request):
    return templates.TemplateResponse('forgot.html', {"request": request, "title": "Forgot Password"})

@router.post('/forgot')
async def forgot(email: str = Form(...)):
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            # Don't reveal if email exists (security)
            return {"ok": True, "message": "If the email exists, a reset link has been sent."}

    token = s.dumps({"email": email})
    reset_link = f"/reset?token={token}"
    send_email(
        email,
        'Reset your password',
        f'<p>Click to reset your password: <a href="{reset_link}">{reset_link}</a></p>'
    )

    if settings.DEBUG:
        print('DEV reset link:', reset_link)

    return {"ok": True, "message": "If the email exists, a reset link has been sent."}

# -------------------------------
# RESET PASSWORD
# -------------------------------
@router.get('/reset', response_class=HTMLResponse)
async def reset_page(request: Request, token: str):
    return templates.TemplateResponse(
        'reset.html',
        {"request": request, "title": "Reset Password", "token": token}
    )

@router.post('/reset')
async def reset(token: str = Form(...), password: str = Form(...)):
    if not validate_password_strength(password):
        raise HTTPException(status_code=400, detail='Weak password')

    try:
        data = s.loads(token, max_age=60 * 60 * 24)  # 24 hours
    except BadSignature:
        raise HTTPException(status_code=400, detail='Invalid or expired token')

    email = data.get('email')
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        user.hashed_password = hash_password(password)
        session.add(AuditLog(user_id=user.id, action='reset_password', meta={'email': email}))
        await session.commit()

    return {"ok": True, "message": "Password reset successfully. Please log in."}
