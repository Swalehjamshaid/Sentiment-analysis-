# filename: app/main.py
from __future__ import annotations
import logging
import os
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

app = FastAPI(title=settings.APP_NAME)

# --- Requirement #4 & #123: Static Files & Directory Safety ---
STATIC_DIR = "app/static"
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")

# Ensure directories exist before mounting to prevent RuntimeError
for path in [STATIC_DIR, UPLOAD_DIR]:
    if not os.path.exists(path):
        logger.info(f"Creating missing directory: {path}")
        os.makedirs(path, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Initialize Jinja2 Templates (Requirement #123)
templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
def on_start():
    logger.info('Initializing database...')
    # Requirement #124: Auto-sync database schema
    init_db(Base)
    
    # Requirement #54: Scheduled Tasks
    try:
        start_scheduler()
        logger.info('Background scheduler active.')
    except Exception as e:
        logger.error(f'Scheduler failed to start: {e}')

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 
        'request': request, 
        'title': settings.APP_NAME 
    })

# Registering All Routers (Requirement #148-155)
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(dashboard.router)
app.include_router(exports.router)
app.include_router(reports.router)
app.include_router(admin.router)
