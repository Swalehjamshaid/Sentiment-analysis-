# filename: app/app/routes/companies.py
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Company
from app.services.google_api import get_place_details

router = APIRouter(tags=['companies'])

@router.post('/companies/create')
def create_company(payload: Dict[str, Any], db: Session = Depends(get_db)):
    data: Dict[str, Any] = {}
    place_id: Optional[str] = payload.get('place_id')
    if place_id:
        details = get_place_details(place_id)
        if not details:
            raise HTTPException(status_code=400, detail='Invalid place_id or Google not configured')
        data.update({
            'name': details.get('name'),
            'address': details.get('formatted_address'),
            'phone': details.get('formatted_phone_number'),
            'website': details.get('website'),
            'google_place_id': place_id,
            'google_url': details.get('url'),
            'state': details.get('administrative_area_level_1'),
            'postal_code': details.get('postal_code'),
            'country': details.get('country'),
            'rating': details.get('rating'),
            'user_ratings_total': details.get('user_ratings_total'),
        })
        types = details.get('types')
        if types:
            import json
            data['types'] = json.dumps(types)
    else:
        if not payload.get('name'):
            raise HTTPException(status_code=422, detail='Missing required field: name')
        allowed = ['name','address','phone','website','google_place_id','google_url','state','postal_code','country','rating','user_ratings_total','types']
        for k in allowed:
            if k in payload:
                data[k] = payload[k]
    obj = Company(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {'ok': True, 'company_id': obj.id}
