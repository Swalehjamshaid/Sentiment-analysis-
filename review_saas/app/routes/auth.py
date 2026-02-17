# app/routes/auth.py

from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import User  # Make sure User model has profile_filename column
from passlib.context import CryptContext

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


@router.post("/register")
def register(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile: UploadFile | None = File(None)  # Profile is optional
):
    with SessionLocal() as db:  # type: Session
        # Check if the user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = get_password_hash(password)

        user = User(
            full_name=full_name,
            email=email,
            password=hashed_password,
            profile_filename=profile.filename if profile and profile.filename else None
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "profile_filename": user.profile_filename
        }
