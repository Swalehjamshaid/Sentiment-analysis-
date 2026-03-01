
# filename: app/routes/companies.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/companies/create")
async def create_company(name: str):
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    # Stub response
    return {"status": "ok", "company": {"name": name}}
