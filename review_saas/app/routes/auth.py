# app/routes/auth.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

@router.post("/register")
def register(data: RegisterRequest):
    # TODO: Add actual database save logic here
    return {"message": "User registered successfully", "user": data.dict()}

@router.post("/login")
def login(username: str, password: str):
    # TODO: Add actual authentication logic here
    return {"username": username, "status": "success"}
