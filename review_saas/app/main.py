# File: review_saas/app/main.py
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Absolute imports are safer for Uvicorn
from app.core.settings import settings
from app.core.db import init_db
from app.models.base import Base
from app.routes import auth, companies, reviews, dashboard, exports, reports, admin
from app.services.scheduler import start_scheduler

# Requirement #130: Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    logger.info('Initializing database...')
    try:
        init_db(Base)
    except Exception as e:
        logger.error(f"Database sync failed: {e}")
        
    # Startup: Background Tasks
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# --- Directory Safety ---
STATIC_DIR = "app/static"
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")

for path in [STATIC_DIR, UPLOAD_DIR]:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory='app/templates')

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 
        'request': request, 
        'title': settings.APP_NAME 
    })

# --- Registering Routers ---
app.include_router(auth.router) 
app.include_router(companies.router, prefix="/companies")
app.include_router(reviews.router, prefix="/reviews")
app.include_router(dashboard.router, prefix="/dashboard")
app.include_router(exports.router, prefix="/exports")
app.include_router(reports.router, prefix="/reports")
app.include_router(admin.router, prefix="/admin")
