# filename: app/routers/companies.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Company

router = APIRouter(prefix="/companies", tags=["companies"])
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal();
    try:
        yield db
    finally:
        db.close()

@router.get("")
async def page(request: Request):
    return templates.TemplateResponse('companies.html', {"request": request})

@router.post('/create')
async def create(request: Request, name: str = Form(...), place_id: str | None = Form(None), city: str | None = Form(None), db: Session = Depends(get_db)):
    if not name and not place_id:
        raise HTTPException(status_code=400, detail="Name or Place ID required")
    comp = Company(name=name, place_id=place_id, city=city)
    db.add(comp); db.commit()
    return {"status":"ok", "id": comp.id}
