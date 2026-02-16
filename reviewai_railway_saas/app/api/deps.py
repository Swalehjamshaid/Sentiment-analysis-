from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import AsyncSessionLocal, settings
from .. import models

security = HTTPBearer()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_db)) -> models.User:
    token = creds.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    q = await db.execute(select(models.User).where(models.User.id == user_id))
    user = q.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user