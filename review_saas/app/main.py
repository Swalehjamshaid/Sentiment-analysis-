# Filename: main.py

import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .db import engine
from .models import Base, Company
from .routes import auth, companies, reviews, reply, reports, dashboard, admin
from .core.config import settings
from .routes.maps_routes import router as maps_router

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
# UI Pages
# ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# ── Fixed: Companies page route (was causing 404) ──
@app.get("/companies", response_class=HTMLResponse)
def companies_page(request: Request):
    return templates.TemplateResponse("companies.html", {"request": request})

@app.get("/report", response_class=HTMLResponse)
def report_page(request: Request):
    return templates.TemplateResponse("report.html", {"request": request})

# ───────────────────────────────────────────────────────────────
# API Routers
# ───────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/auth")
app.include_router(companies.router)  # ← connects /companies API
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
