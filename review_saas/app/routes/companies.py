# app/routes/companies.py

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company
from fastapi import Depends

router = APIRouter(prefix="/companies", tags=["companies"])

@router.get("/")
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()
