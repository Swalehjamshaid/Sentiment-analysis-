# filename: app/main.py
import os
import asyncio
import logging
from datetime import datetime
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

# ----------------------------------------------------------
# CORE IMPORTS
# ----------------------------------------------------------
from app.core.config import settings
from app.core.db import init_models, get_db

# ----------------------------------------------------------
# LOGGING & AUTH
# ----------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ----------------------------------------------------------
# LIFESPAN (Database Initialization)
# ----------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--------------------------------------------------")
    logger.info("🚀 Starting Review Intel AI | Initializing Systems")
    logger.info("--------------------------------------------------")
    
    try:
        # Executes the "Stegman Rule" Nuclear Reset from db.py
        await init_models() 
        logger.info("✅ Database systems synchronized.")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        
    yield
    logger.info("🛑 Shutdown complete.")

# ----------------------------------------------------------
# APP INIT
# ----------------------------------------------------------
app = FastAPI(
    title="Review Intel AI",
    lifespan=lifespan,
)

# ----------------------------------------------------------
# MIDDLEWARE
# ----------------------------------------------------------
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

# -----------------------------------------------------------------------------
# ⭐ THE MULTI-PATH TEMPLATE & JINJA FILTER FIX
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# We search multiple paths to ensure Railway finds the templates folder
possible_paths = [
    os.path.join(BASE_DIR, "templates"), # /app/templates
    os.path.join(os.getcwd(), "app", "templates"), # /review_saas/app/templates
    "templates" # relative fallback
]

template_path = None
for path in possible_paths:
    if os.path.isdir(path):
        template_path = path
        break

if not template_path:
    # If all else fails, default to the standard absolute path
    template_path = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=template_path)
logger.info(f"🚀 JINJA2 ACTIVE: Templates found at {template_path}")

# REGISTER THE 'date' FILTER (Prevents crash on dashboard)
def format_date(value, format="%Y-%m-%d"):
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except:
            return value
    return value.strftime(format)

templates.env.filters["date"] = format_date

# BULLETPROOF STATIC PATHING
static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"📁 Static files mounted from: {static_dir}")
else:
    logger.warning(f"⚠️ static/ directory not found at {static_dir}")

# ----------------------------------------------------------
# ROUTE IMPORTS (LOCALIZED TO PREVENT CIRCULAR LOOPS)
# ----------------------------------------------------------
from app.routes import auth, companies, dashboard, reviews

# ----------------------------------------------------------
# UI ROUTES (UNCHANGED LOGIC)
# ----------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(
        "/dashboard" if request.session.get("user") else "/login"
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # This uses the 'templates' object with the discovered path
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
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

# ----------------------------------------------------------
# API ROUTES (UNCHANGED LOGIC)
# ----------------------------------------------------------
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])

# ----------------------------------------------------------
# ENTRYPOINT
# ----------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
