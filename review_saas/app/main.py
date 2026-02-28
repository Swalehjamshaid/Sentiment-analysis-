# filename: app/main.py

import os
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .core.config import settings
from .db import init_db_sync
from .models import Base
from .routers import auth as auth_router
from .routers import companies as companies_router
from .routers import dashboard as dashboard_router

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

# App init
app = FastAPI(title="ReviewSaaS")
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET)

# Static files
STATIC_DIR = "app/static"
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info("Static directory mounted.")
else:
    logger.warning("Static directory not found. Skipping static mount.")

# Templates
TEMPLATES_DIR = "app/templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Startup
@app.on_event("startup")
def startup():
    logger.info("Initializing database...")
    init_db_sync(Base)
    logger.info("Application startup complete.")

# Routes
@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Include routers
app.include_router(auth_router.router)
app.include_router(companies_router.router)
app.include_router(dashboard_router.router)
