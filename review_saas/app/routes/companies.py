from fastapi import APIRouter, Depends, HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from ..db import get_session
    from ..models import Company
    from ..schemas import CompanyIn

    router = APIRouter(prefix="/companies", tags=["companies"])

    @router.post("")
    async def create_company(payload: CompanyIn, session: AsyncSession = Depends(get_session)):
        if not (payload.name or payload.place_id or payload.maps_link):
            raise HTTPException(status_code=400, detail="Provide name or Place ID/Link")
        comp = Company(name=payload.name or "Unnamed", place_id=payload.place_id, maps_link=payload.maps_link, city=payload.city)
        session.add(comp)
        await session.commit()
        return {"id": comp.id, "name": comp.name}

    @router.get("")
    async def list_companies(session: AsyncSession = Depends(get_session)):
        rows = (await session.execute(select(Company))).scalars().all()
        return [{"id": c.id, "name": c.name, "city": c.city, "status": c.status} for c in rows]