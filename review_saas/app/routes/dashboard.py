# app/routes/dashboard.py

from fastapi import APIRouter
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/")
def get_dashboard():
    return {"message": "Dashboard data here"}
