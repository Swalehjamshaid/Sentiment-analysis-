from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_session
from ..models import User
from ..schemas import UserCreate, UserLogin
from ..utils.security import hash_password, verify_password, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    # uniqueness check
    exists = (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password)
    )
    session.add(user)
    await session.commit()
    return {"id": user.id, "email": user.email}


@router.post("/login")
async def login(payload: UserLogin, session: AsyncSession = Depends(get_session)):
    user = (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    token = issue_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}
