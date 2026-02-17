from fastapi import APIRouter, HTTPException, Depends
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import and_
    from ..db import engine
    from ..models import Company, User
    from ..utils.security import get_current_user_id
    from ..services.places import validate_place_id

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/companies", tags=["companies"])

    @router.post("")
    async def add_company(name: str | None = None, maps_link: str | None = None, place_id: str | None = None, city: str | None = None, user_id: int = Depends(get_current_user_id)):
        if not (name or maps_link or place_id):
            raise HTTPException(400, "Provide Name or Maps link or Place ID")
        if place_id and not await validate_place_id(place_id):
            raise HTTPException(400, "Invalid Google Place ID")
        with SessionLocal() as s:
            if place_id:
                dup = s.query(Company).filter(and_(Company.owner_id==user_id, Company.place_id==place_id)).first()
                if dup: raise HTTPException(400, "Company exists (place_id)")
            if name:
                dup2 = s.query(Company).filter(and_(Company.owner_id==user_id, Company.name==name, Company.city==city)).first()
                if dup2: raise HTTPException(400, "Company exists (name/city)")
            c = Company(owner_id=user_id, name=name or "Unnamed", maps_link=maps_link, place_id=place_id, city=city)
            s.add(c); s.commit(); s.refresh(c)
            return {"id": c.id}

    @router.get("")
    def list_companies(q: str | None = None, status: str | None = None, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            query = s.query(Company).filter(Company.owner_id==user_id)
            if q:
                like = f"%{q}%"
                query = query.filter((Company.name.like(like)) | (Company.city.like(like)) | (Company.place_id.like(like)))
            if status:
                query = query.filter(Company.status==status)
            rows = query.order_by(Company.created_at.desc()).all()
            return [{"id": c.id, "name": c.name, "city": c.city, "status": c.status, "place_id": c.place_id} for c in rows]

    @router.put("/{company_id}")
    def update_company(company_id: int, name: str | None = None, city: str | None = None, status: str | None = None, user_id: int = Depends(get_current_user_id)):
        with SessionLocal() as s:
            c = s.get(Company, company_id)
            if not c or c.owner_id != user_id: raise HTTPException(404, "Not found")
            if name is not None: c.name = name
            if city is not None: c.city = city
            if status is not None: c.status = status
            s.commit(); s.refresh(c)
            return {"updated": c.id}

    @router.delete("/{company_id}")
    def delete_company(company_id: int, confirm: bool = False, user_id: int = Depends(get_current_user_id)):
        if not confirm: raise HTTPException(400, "Confirmation required")
        with SessionLocal() as s:
            c = s.get(Company, company_id)
            if not c or c.owner_id != user_id: raise HTTPException(404, "Not found")
            s.delete(c); s.commit(); return {"deleted": company_id}