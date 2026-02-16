from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import AsyncSessionLocal
from .. import models
from .deps import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    users_count = (await db.execute(select(func.count(models.User.id)))).scalar_one()
    companies_count = (await db.execute(select(func.count(models.Company.id)))).scalar_one()
    reviews_count = (await db.execute(select(func.count(models.Review.id)))).scalar_one()
    return {"users": users_count, "companies": companies_count, "reviews": reviews_count}