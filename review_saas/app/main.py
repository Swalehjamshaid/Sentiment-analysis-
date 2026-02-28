# filename: app/main.py
from __future__ import annotations
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from .core.settings import settings
from .core.db import init_db
from .models.base import Base
from .routes import auth, companies, reviews, dashboard, exports, reports, admin
from .services.scheduler import start_scheduler

# Configure Logging (Requirement #130)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger('review_saas')

app = FastAPI(title=settings.APP_NAME)

# Requirement #4 & #123: Mount static files for CSS, JS, and Profile Pictures
# Ensure the folder 'app/static' exists in your project
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize Jinja2 Templates (Requirement #123)
templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
def on_start():
    logger.info('Initializing database...')
    # Requirement #124: Auto-create tables on startup
    init_db(Base)
    
    # Requirement #54: Start scheduled review fetching (Daily/Weekly)
    try:
        start_scheduler()
        logger.info('Background scheduler started successfully.')
    except Exception as e:
        logger.error(f'Failed to start scheduler: {e}')

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    # Requirement #148: Landing Page
    return templates.TemplateResponse('index.html', { 
        'request': request, 
        'title': settings.APP_NAME 
    })

# Registering Routers (Requirement #148-155 Workflow)
# Note: Ensure routers inside these files do not have conflicting prefixes
app.include_router(auth.router)       # Handles /login, /register, /verify
app.include_router(companies.router)  # Handles /companies/add, etc.
app.include_router(reviews.router)    # Handles /reviews/fetch
app.include_router(dashboard.router)  # Handles /dashboard
app.include_router(exports.router)    # Handles /exports/csv
app.include_router(reports.router)    # Handles /reports/pdf
app.include_router(admin.router)      # Handles /admin (Requirement #115)

# Middleware for HTTPS enforcement (Requirement #18)
@app.middleware("http")
async def enforce_https_middleware(request: Request, call_next):
    # If deployed on Railway/Heroku, they handle SSL termination
    # But we check the header to be sure
    if settings.COOKIE_SECURE and request.headers.get("x-forwarded-proto") == "http":
        return HTMLResponse("HTTPS Required", status_code=403)
    return await call_next(request)
