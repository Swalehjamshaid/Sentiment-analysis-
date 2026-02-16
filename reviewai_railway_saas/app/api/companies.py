from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import AsyncSessionLocal
from .. import models, schemas
from .deps import get_current_user

router = APIRouter(prefix="/companies", tags=["companies"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.post("/", response_model=schemas.CompanyOut)
async def add_company(payload: schemas.CompanyCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    obj = models.Company(
        user_id=user.id,
        name=payload.name,
        google_place_id=payload.google_place_id,
        maps_link=payload.maps_link,
        city=payload.city,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.get("/", response_model=list[schemas.CompanyOut])
async def list_companies(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.execute(select(models.Company).where(models.Company.user_id == user.id))
    return [c for c in q.scalars().all()]