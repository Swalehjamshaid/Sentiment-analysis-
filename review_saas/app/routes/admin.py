# File 7: admin.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Company, Review
import csv, io
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/admin", tags=["Admin"])

def admin_required(current_user: User = Depends()):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@router.get("/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(admin_required)):
    users = db.query(User).all()
    return users

@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(admin_required)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"detail": "User deleted"}

@router.get("/export/companies")
def export_companies_csv(db: Session = Depends(get_db), current_user: User = Depends(admin_required)):
    companies = db.query(Company).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Company ID","User ID","Name","Place ID","City","Status","Logo URL","Date Added"])
    for c in companies:
        writer.writerow([c.id, c.user_id, c.name, c.place_id, c.city, c.status, c.logo_url, c.date_added])
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=companies.csv"})
