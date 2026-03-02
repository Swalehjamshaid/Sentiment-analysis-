from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.db import get_db
from app.core.security import get_current_user
from app.services.google_api import google_api_service
from pydantic import BaseModel

router = APIRouter()

# --- Pydantic Schemas for Validation ---
class CompanyBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None
    category: Optional[str] = None
    place_id: str

class CompanyCreate(CompanyBase):
    pass

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None
    status: Optional[str] = None

# --- Routes ---

@router.get("/search", response_model=dict)
async def search_google_company(query: str, current_user=Depends(get_current_user)):
    """
    Requirement: Integrate with Google Places API to search companies by name.
    """
    result = google_api_service.search_company_by_name(query)
    if not result:
        raise HTTPException(status_code=404, detail="No company found on Google Maps")
    
    # Requirement: Auto-fill details including name, address, category
    details = google_api_service.get_company_details(result['place_id'])
    return details

@router.post("/add", status_code=status.HTTP_201_CREATED)
async def add_company(company: CompanyCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Requirement: Allow users to add companies to the dashboard and store Google Place ID.
    """
    # Logic to save to your SQLAlchemy Model (e.g., Company)
    # new_company = Company(**company.dict(), owner_id=current_user.id)
    # db.add(new_company)
    # db.commit()
    return {"message": "Company added successfully", "data": company}

@router.put("/update/{company_id}")
async def update_company(company_id: int, updates: CompanyUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Requirement: Allow manual editing of auto-filled company data.
    """
    # Logic to find company by ID and update fields
    return {"message": "Company updated successfully"}

@router.delete("/delete/{company_id}")
async def delete_company(company_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Requirement: Allow users to delete companies with confirmation.
    """
    # Logic to delete company from DB
    return {"message": "Company deleted successfully"}
