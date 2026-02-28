from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from .core.settings import settings
from .core.db import init_db
from .models.base import Base
from .routes import auth, companies, reviews, dashboard, exports, reports, admin
from .services.scheduler import start_scheduler

# Requirement #130: Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')

# --- Lifespan Management (Requirement #124 & #54) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Logic
    logger.info('Initializing database...')
    init_db(Base)
    
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')
    
    yield
    # Shutdown logic (if needed) can go here

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# --- Requirement #4 & #123: Static Files & Directory Safety ---
STATIC_DIR = "app/static"
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")

for path in [STATIC_DIR, UPLOAD_DIR]:
    if not os.path.exists(path):
        logger.info(f"Creating missing directory: {path}")
        os.makedirs(path, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory='app/templates')

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 
        'request': request, 
        'title': settings.APP_NAME 
    })

# --- Registering All Routers (Requirement #148-155) ---
# Ensure auth is included first. 
# Check app/routes/auth.py to ensure the route is @router.get("/register") 
# and NOT @router.get("/") with a prefix.
app.include_router(auth.router, tags=["Authentication"]) 
app.include_router(companies.router, prefix="/companies", tags=["Companies"])
app.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(exports.router, prefix="/exports", tags=["Exports"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
