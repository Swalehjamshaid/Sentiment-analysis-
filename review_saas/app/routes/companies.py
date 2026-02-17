from fastapi import APIRouter, HTTPException
    from sqlalchemy.orm import sessionmaker
    from ..db import engine
    from ..models import Company

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/companies", tags=["companies"])

    @router.post("")
    def add_company(name: str | None = None, maps_link: str | None = None, place_id: str | None = None, city: str | None = None):
        if not (name or maps_link or place_id):
            raise HTTPException(status_code=400, detail="Provide Name or Maps link or Place ID")
        with SessionLocal() as s:
            # basic duplicate prevention by name+city
            q = s.query(Company).filter(Company.name==name, Company.city==city)
            if name and q.first():
                raise HTTPException(status_code=400, detail="Company already exists")
            c = Company(name=name or "Unnamed", maps_link=maps_link, place_id=place_id, city=city)
            s.add(c); s.commit()
            return {"id": c.id}

    @router.get("")
    def list_companies(q: str | None = None, status: str | None = None):
        with SessionLocal() as s:
            query = s.query(Company)
            if q:
                like = f"%{q}%"
                query = query.filter((Company.name.like(like)) | (Company.city.like(like)) | (Company.place_id.like(like)))
            if status:
                query = query.filter(Company.status==status)
            rows = query.order_by(Company.created_at.desc()).all()
            return [
                {"id": c.id, "name": c.name, "city": c.city, "status": c.status, "place_id": c.place_id}
                for c in rows
            ]

    @router.delete("/{company_id}")
    def delete_company(company_id: int, confirm: bool = False):
        if not confirm:
            raise HTTPException(status_code=400, detail="Confirmation required")
        with SessionLocal() as s:
            c = s.get(Company, company_id)
            if not c:
                raise HTTPException(status_code=404, detail="Not found")
            s.delete(c); s.commit()
            return {"deleted": company_id}