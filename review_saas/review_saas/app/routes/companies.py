
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..models import Company
from ..schemas import CompanyCreate, CompanyOut
from ..services.google_places import validate_place_id

router = APIRouter(prefix='/companies', tags=['companies'])

@router.post('/')
async def add_company(payload: CompanyCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not (payload.name or payload.place_id or payload.maps_url):
        raise HTTPException(status_code=400, detail='Provide at least one: name, place_id, or maps_url')

    place_id = payload.place_id
    if payload.maps_url and not place_id:
        # naive extraction
        import re
        m = re.search(r'place_id=([A-Za-z0-9_-]+)', payload.maps_url)
        if m:
            place_id = m.group(1)

    # Validate place ID if present
    if place_id:
        try:
            await validate_place_id(place_id)
        except Exception:
            raise HTTPException(status_code=400, detail='Invalid Google Place ID')

    comp = Company(owner_user_id=current_user.id, name=(payload.name or '').strip() or None, place_id=place_id, maps_url=payload.maps_url, city=payload.city)
    db.add(comp)
    try:
        db.commit(); db.refresh(comp)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail='Duplicate company for this user')
    return {'id': comp.id}

@router.get('/')
async def list_companies(q: str | None = None, city: str | None = None, status: str | None = None, place_id: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Company).filter(Company.owner_user_id==current_user.id)
    if q:
        query = query.filter(Company.name.ilike(f'%{q}%'))
    if city:
        query = query.filter(Company.city.ilike(f'%{city}%'))
    if status:
        query = query.filter(Company.status == status)
    if place_id:
        query = query.filter(Company.place_id == place_id)
    return [
        {
            'id': c.id,
            'name': c.name,
            'place_id': c.place_id,
            'maps_url': c.maps_url,
            'city': c.city,
            'status': c.status,
            'logo_url': c.logo_url,
            'created_at': c.created_at.isoformat()
        } for c in query.all()
    ]

@router.delete('/{company_id}')
async def delete_company(company_id: int, confirm: bool = False, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not confirm:
        raise HTTPException(status_code=400, detail='Please confirm deletion')
    c = db.query(Company).get(company_id)
    if c and c.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Forbidden')
    if c and c.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Forbidden')
    if not c:
        raise HTTPException(status_code=404, detail='Not found')
    db.delete(c); db.commit()
    return {'message': 'Deleted'}

@router.put('/{company_id}')
async def edit_company(company_id: int, payload: CompanyCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    c = db.query(Company).get(company_id)
    if c and c.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Forbidden')
    if c and c.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail='Forbidden')
    if not c:
        raise HTTPException(status_code=404, detail='Not found')
    if payload.name is not None: c.name = payload.name
    if payload.city is not None: c.city = payload.city
    if payload.maps_url is not None: c.maps_url = payload.maps_url
    db.commit()
    return {'message': 'Updated'}
