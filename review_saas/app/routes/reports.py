# app/routes/reports.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import engine, get_db
from ..models import Report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/")
def list_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).all()
    return reports
