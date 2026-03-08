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
    check_rate_limit(request, f"reg:{request.client.host}")

    if not validate_password_strength(password):
        raise HTTPException(status_code=400, detail='Weak password')

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
        exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=400, detail='Email already registered')

        # Simple: Set email_verified to True immediately
        u = User(
            name=name,
            email=email,
            hashed_password=hash_password(password),
            profile_pic=pic_path,
            role='editor',
            email_verified=True 
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)

        session.add(AuditLog(user_id=u.id, action='register', meta={'email': email}))
        await session.commit()

    # No verification email sent, go straight to login
    return RedirectResponse(url='/login?msg=success', status_code=302)

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
        
        # Simple credentials check
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        request.session['user_id'] = user.id
        request.session['role'] = user.role
        token = create_access_token(str(user.id), extra={"role": user.role})

        session.add(AuditLog(user_id=user.id, action='login', meta={'email': email}))
        await session.commit()

    resp = RedirectResponse(url='/dashboard', status_code=302)
    resp.set_cookie('access_token', token, httponly=True, samesite='lax')
    return resp

# -------------------------------
# LOGOUT
# -------------------------------
@router.get('/logout')
async def logout(request: Request):
    uid = request.session.get('user_id')
    request.session.clear()

    if uid:
        async with get_session() as session:
            session.add(AuditLog(user_id=uid, action='logout', meta={}))
            await session.commit()

    resp = RedirectResponse(url='/', status_code=302)
    resp.delete_cookie('access_token')
    return resp

# ... (Forgot/Reset logic removed for simplicity, add back if needed)
