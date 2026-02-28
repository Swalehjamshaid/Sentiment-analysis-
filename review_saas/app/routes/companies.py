
# filename: app/routes/companies.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..models.models import Company

router = APIRouter(prefix='/companies', tags=['companies'])

@router.post('')
def create_company(name: str, place_id: str | None = None, city: str | None = None, db: Session = Depends(get_db)):
    if not name and not place_id:
        raise HTTPException(status_code=400, detail='Name or place_id required')
    obj = Company(name=name, place_id=place_id, city=city)
    db.add(obj); db.commit(); db.refresh(obj)
    return {'id': obj.id}

@router.get('')
def list_companies(db: Session = Depends(get_db)):
    return [{'id': c.id, 'name': c.name, 'place_id': c.place_id} for c in db.query(Company).all()]
