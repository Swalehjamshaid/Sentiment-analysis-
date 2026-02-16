# review_saas/app/main.py
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os

from .config import ALLOWED_ORIGINS, HTTPS_ONLY
from .db import Base, engine
from . import models

# Routers (API)
from .auth import router as auth_router
from .routes.companies import router as companies_router
from .routes.reviews import router as reviews_router
from .routes.replies import router as replies_router
from .routes.dashboard import router as dashboard_router
from .routes.admin import router as admin_router
from .routes.reports import router as reports_router
from .routes.jobs import router as jobs_router
from .routes.alerts import router as alerts_router

app = FastAPI(title="Reputation Management SaaS")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Ensure runtime directories ----------
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

# ---------- Static mounts ----------
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- Templates ----------
templates = Jinja2Templates(directory="templates")

# ---------- DB init ----------
Base.metadata.create_all(bind=engine)

# ---------- API routers ----------
app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(reviews_router)
app.include_router(replies_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(jobs_router)
app.include_router(alerts_router)

# ---------- Redirect root to UI (so site opens as a web page) ----------
@app.get("/", include_in_schema=False)
async def redirect_root():
    return RedirectResponse(url="/home", status_code=307)

# ---------- UI routes (HTML) ----------
@app.get("/home")
async def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/ui/auth")
async def auth_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/ui/companies")
async def companies_page(request: Request):
    return templates.TemplateResponse("companies.html", {"request": request})

@app.get("/ui/dashboard/{company_id}")
async def dashboard_page(company_id: int, request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "company_id": company_id})

# ---------- Favicon (no 404 noise) ----------
@app.get("/favicon.ico")
async def favicon():
    path = os.path.join("static", "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/x-icon")
    return Response(status_code=204)

# ---------- HTTPS enforcement (prod) ----------
@app.middleware("http")
async def https_enforce(request: Request, call_next):
    if HTTPS_ONLY and request.url.scheme != "https":
        return Response("HTTPS required", status_code=400)
    return await call_next(request)
