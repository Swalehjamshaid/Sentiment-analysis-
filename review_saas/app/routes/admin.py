# app/routes/admin.py

from fastapi import APIRouter
router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/")
def admin_panel():
    return {"message": "Admin panel"}
