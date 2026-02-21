# Filename: main.py

import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .db import engine
from .models import Base, Company
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .core.config import settings
from .routes.maps_routes import router as maps_router
from .routes.auth import get_current_user   # ✅ FIXED IMPORT


# ───────────────────────────────────────────────────────────────
# HTTPS Redirect Middleware
# ───────────────────────────────────────────────────────────────
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and proto != "https":
            url = request.url.replace(scheme="https")
            return RedirectResponse(url, status_code=307)
        return await call_next(request)


# ───────────────────────────────────────────────────────────────
# FastAPI app initialization
# ───────────────────────────────────────────────────────────────
app = FastAPI(title=settings.APP_NAME)
templates = Jinja2Templates(directory="app/templates")

app.add_middleware(HTTPSRedirectMiddleware)

if os.path.isdir("app_uploads"):
    app.mount("/uploads", StaticFiles(directory="app_uploads"), name="uploads")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ───────────────────────────────────────────────────────────────
# Database initialization
# ───────────────────────────────────────────────────────────────
@app.on_event("startup")
def _init_db():
    Base.metadata.create_all(bind=engine)

    # ONE-TIME SCHEMA FIX – use environment variable RECREATE_COMPANIES=1
    if os.getenv("RECREATE_COMPANIES") == "1":
        print("!!! DROPPING AND RECREATING COMPANIES TABLE !!!")
        Base.metadata.drop_all(bind=engine, tables=[Company.__table__])
        Base.metadata.create_all(bind=engine)
        print("Companies table recreated with owner_id, lat, lng columns.")


# ───────────────────────────────────────────────────────────────
# Helper: inject current_user + current_year into templates
# ───────────────────────────────────────────────────────────────
def template_context(
    request: Request,
    current_user: Optional[Company] = Depends(get_current_user)
):
    return {
        "request": request,
        "current_user": current_user,
        "current_year": datetime.now().year,  # ✅ prevents footer error
    }


# ───────────────────────────────────────────────────────────────
# UI Pages
# ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(context: dict = Depends(template_context)):
    return templates.TemplateResponse("home.html", context)


@app.get("/register", response_class=HTMLResponse)
def register_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("register.html", context)


@app.get("/login", response_class=HTMLResponse)
def login_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("login.html", context)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/companies", response_class=HTMLResponse)
def companies_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("companies.html", context)


@app.get("/report", response_class=HTMLResponse)
def report_page(context: dict = Depends(template_context)):
    return templates.TemplateResponse("report.html", context)


# ───────────────────────────────────────────────────────────────
# API Routers
# ───────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/auth")
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(reply.router)
app.include_router(reports.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(maps_router)


# ───────────────────────────────────────────────────────────────
# Health check
# ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True}
