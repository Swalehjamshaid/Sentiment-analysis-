# filename: app/app/routes/auth.py
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
import hashlib, os

router = APIRouter(tags=["auth"])
SALT = os.getenv('AUTH_SALT', 'static-salt')

def hash_password(p: str) -> str:
    return hashlib.sha256((SALT + p).encode('utf-8')).hexdigest()

@router.get('/login')
async def login_view():
    return RedirectResponse('/dashboard?show=login', status_code=HTTP_302_FOUND)

@router.post('/login')
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or user.password_hash != hash_password(password):
        return RedirectResponse('/dashboard?show=login', status_code=HTTP_302_FOUND)
    request.session['user'] = {'id': user.id, 'email': user.email, 'name': user.name}
    return RedirectResponse('/dashboard?show=dashboard', status_code=HTTP_302_FOUND)

@router.get('/register')
async def register_view():
    return RedirectResponse('/dashboard?show=register', status_code=HTTP_302_FOUND)

@router.post('/register')
async def register_submit(request: Request, email: str = Form(...), password: str = Form(...), name: str = Form(''), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return RedirectResponse('/dashboard?show=login', status_code=HTTP_302_FOUND)
    user = User(name=name, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    return RedirectResponse('/dashboard?show=login&registered=1', status_code=HTTP_302_FOUND)

@router.post('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/dashboard?show=login', status_code=HTTP_302_FOUND)
