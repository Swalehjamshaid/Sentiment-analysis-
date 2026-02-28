# filename: app/routers/auth.py

from fastapi import APIRouter, Request, Depends, Form, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets

from ..core.config import settings
from ..security.utils import verify_password_strength, hash_password, verify_password, create_access_token
from ..models import User, VerificationToken, LoginAttempt
from ..db import SessionLocal
from ..emailer import send_email

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


# ----------------
