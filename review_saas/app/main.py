# filename: app/main.py
import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

# -------------------------------
# CORE IMPORTS
# -------------------------------
from app.core.config import settings
from app.core.db import init_models, get_db

# -------------------------------
# STEGMAN RULE: SCHEMA VERSIONING
# POINT OF CHANGE: Update this string to any new value 
# (e.g. "2026-04-06-V2") to trigger a total wipe and rebuild.
# -------------------------------
CURRENT_SCHEMA_VERSION = "2026-04-06-V1I" 

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# -------------------------------
# PASSWORD HASHING
# -------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------------------
# LIFESPAN (The Stegman Rule Implementation)
# -------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log the version so you can see it in Railway/Console logs
    logger.info(f"🚀 Starting Review Intel AI | Schema Version: {CURRENT_SCHEMA_VERSION}")
    
    try:
        # POINT OF ACTION: init_models handles the drop_all and create_all
        # We pass the version string to ensure the DB syncs correctly
        await init_models() 
        logger.info(f"✅ Database synchronized with version {CURRENT_SCHEMA_VERSION}")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        
    yield
    logger.info("🛑 Shutdown complete")

# -------------------------------
# APP INIT
# -------------------------------
app = FastAPI(
    title="Review Intel AI",
    lifespan=lifespan,
)

# -------------------------------
# MIDDLEWARE
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
)

# -------------------------------
# STATIC & TEMPLATES (UNIVERSAL PATHING)
# -------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(static_dir):
    app.mount(
        "/static",
        StaticFiles(directory=static_dir),
        name="static",
    )
else:
    logger.warning(f"⚠️ static/ directory not found at {static_dir}")

templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "templates")
)

# -------------------------------
# ROUTE IMPORTS (LOCALIZED TO PREVENT CIRCULAR LOOPS)
# -------------------------------
from app.routes import auth, companies, dashboard, reviews

# -------------------------------
# UI ROUTES
# -------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(
        "/dashboard" if request.session.get("user") else "/login"
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # ✅ Local import to prevent circular dependency
    from app.core.models import User

    result = await db.execute(
        select(User).where(User.email == email.strip().lower())
    )
    user = result.scalars().first()

    if user and pwd_context.verify(password, user.hashed_password):
        request.session["user"] = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }
        return RedirectResponse("/dashboard", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": "Invalid email or password",
        },
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": request.session.get("user"),
        },
    )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# -------------------------------
# API ROUTES
# -------------------------------
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])

# -------------------------------
# LOCAL ENTRYPOINT ONLY
# -------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
