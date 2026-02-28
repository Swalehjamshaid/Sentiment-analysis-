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


# -------------------------------------------------------
# LOGGING
# -------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

# -------------------------------------------------------
# APP INIT
# -------------------------------------------------------
app = FastAPI(title="ReviewSaaS")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET
)

# -------------------------------------------------------
# STATIC FILES (SAFE MOUNT)
# -------------------------------------------------------
STATIC_DIR = "app/static"
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info("Static directory mounted.")
else:
    logger.warning("Static directory not found. Skipping static mount.")

# -------------------------------------------------------
# TEMPLATES (SAFE LOAD)
# -------------------------------------------------------
TEMPLATES_DIR = "app/templates"
if os.path.isdir(TEMPLATES_DIR):
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
else:
    templates = None
    logger.warning("Templates directory not found.")

# -------------------------------------------------------
# STARTUP EVENT
# -------------------------------------------------------
@app.on_event("startup")
def startup():
    logger.info("Initializing database...")
    init_db_sync(Base)
    logger.info("Application startup complete.")

# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.get("/")
def index(request: Request):
    if not templates:
        return {"message": "ReviewSaaS API Running"}
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

app.include_router(auth_router.router)
app.include_router(companies_router.router)
app.include_router(dashboard_router.router)
