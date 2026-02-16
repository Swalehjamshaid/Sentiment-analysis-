from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import AsyncSessionLocal
from .. import models, schemas
from ..auth.security import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/register", response_model=schemas.UserOut)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == user.email))
    if q.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    obj = models.User(name=user.name, email=user.email, password_hash=get_password_hash(user.password))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.post("/login", response_model=schemas.Token)
async def login(form: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(models.User).where(models.User.email == form.email))
    user = q.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    return {"access_token": token, "token_type": "bearer"}