# File 1: company.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import os
from ..db import get_db
from ..models import Company, User
from ..schemas import CompanyCreate, CompanyUpdate
import requests

router = APIRouter(prefix="/company", tags=["Company"])

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

def validate_place_id(place_id: str):
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={GOOGLE_PLACES_API_KEY}"
    resp = requests.get(url)
    data = resp.json()
    if data.get("status") != "OK":
        raise HTTPException(status_code=400, detail="Invalid Google Place ID")
    return True

@router.post("/")
def add_company(company: CompanyCreate, db: Session = Depends(get_db), current_user: User = Depends()):
    if company.place_id:
        validate_place_id(company.place_id)

    exists = db.query(Company).filter_by(user_id=current_user.id, name=company.name).first()
    if exists:
        raise HTTPException(status_code=400, detail="Company already exists")
    
    db_company = Company(
        user_id=current_user.id,
        name=company.name,
        place_id=company.place_id,
        city=company.city,
        logo_url=company.logo_url,
        status="Active"
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company

@router.put("/{company_id}")
def update_company(company_id: int, company: CompanyUpdate, db: Session = Depends(get_db), current_user: User = Depends()):
    db_company = db.query(Company).filter_by(id=company_id, user_id=current_user.id).first()
    if not db_company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    for field, value in company.dict(exclude_unset=True).items():
        setattr(db_company, field, value)
    
    db.commit()
    db.refresh(db_company)
    return db_company

@router.delete("/{company_id}")
def delete_company(company_id: int, db: Session = Depends(get_db), current_user: User = Depends()):
    db_company = db.query(Company).filter_by(id=company_id, user_id=current_user.id).first()
    if not db_company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    db.delete(db_company)
    db.commit()
    return {"detail": "Company deleted successfully"}
