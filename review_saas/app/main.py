import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from sqlalchemy import select
from passlib.context import CryptContext

# Absolute path resolution for Docker/Railway compatibility
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.db import init_models, get_db, SessionLocal, engine
from app.core import models
from app.core.models import User, SCHEMA_VERSION, Config as ConfigModel
from app.routes import auth, companies, dashboard, reviews, exports, google_check

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app.main")

async def _get_stored_schema_version(session):
    res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
    row = res.scalar_one_or_none()
    return row.value if row else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI...")
    await init_models()
    async with SessionLocal() as session:
        old_v = await _get_stored_schema_version(session)
        if old_v != str(SCHEMA_VERSION):
            logger.warning(f"🧩 Schema Change Detected: {old_v} -> {SCHEMA_VERSION}. Resetting DB...")
            async with engine.begin() as conn:
                await conn.run_sync(models.Base.metadata.drop_all)
                await conn.run_sync(models.Base.metadata.create_all)
            
            # Update Version Key
            res = await session.execute(select(ConfigModel).where(ConfigModel.key == "SCHEMA_VERSION"))
            row = res.scalar_one_or_none()
            if row: row.value = str(SCHEMA_VERSION)
            else: session.add(ConfigModel(key="SCHEMA_VERSION", value=str(SCHEMA_VERSION)))
            await session.commit()
    yield
    logger.info("🛑 Shutting down...")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static & Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- Helper: Current User ---
def get_current_user(request: Request):
    return request.session.get("user")

# --- Core Routes ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if get_current_user(request):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, message: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "message": message})

@app.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...), db=Depends(get_db)):
    email_clean = email.strip().lower()
    res = await db.execute(select(User).where(User.email == email_clean))
    user = res.scalars().first()
    
    if user and pwd_context.verify(password, user.hashed_password):
        if not user.is_verified:
            return templates.TemplateResponse("login.html", {
                "request": request, 
                "error": "Account not verified. Please check your email."
            })
        
        request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
        return RedirectResponse("/dashboard", status_code=303)
    
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password."})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user,
        "schema_version": getattr(app.state, "schema_version", SCHEMA_VERSION)
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# Mount Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
