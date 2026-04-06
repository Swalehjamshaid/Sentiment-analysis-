# filename: app/main.py
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
import hashlib
import json

from app.core.config import settings
from app.core.db import init_models, get_db, engine
from app.routes import auth, companies, dashboard, reviews, exports, google_check

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SCHEMA_FILE = "schema_version.json"  # store last known schema hash

async def compute_schema_hash():
    """Compute a simple hash of all table names in the current metadata"""
    from app.core import models
    tables = sorted(models.Base.metadata.tables.keys())
    return hashlib.sha256(json.dumps(tables).encode()).hexdigest()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Fresh Start Sequence Initiated...")

    try:
        current_hash = await compute_schema_hash()
        previous_hash = None

        if os.path.exists(SCHEMA_FILE):
            with open(SCHEMA_FILE, "r") as f:
                previous_hash = json.load(f).get("hash")

        if previous_hash != current_hash:
            print("⚡ Schema change detected — rebuilding tables...")
            await init_models()  # Drops and recreates all tables
            with open(SCHEMA_FILE, "w") as f:
                json.dump({"hash": current_hash}, f)
        else:
            print("✅ Schema unchanged — skipping table rebuild.")
    except Exception as e:
        print(f"❌ Startup Failed: {e}")

    yield

# ----- FastAPI App -----
app = FastAPI(title="Review Intel AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# ----- Static & Templates -----
APP_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# ----- Login -----
@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    from app.core.models import User
    res = await db.execute(select(User).where(User.email == email.strip().lower()))
    user = res.scalars().first()
    if user and pwd_context.verify(password, user.hashed_password):
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid login"}
    )

# ----- Include Routers -----
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])
