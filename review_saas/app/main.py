# review_saas/app/main.py
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates  # NEW: Jinja2 renderer
import os

from .config import ALLOWED_ORIGINS, HTTPS_ONLY
from .db import Base, engine
from . import models
from .auth import router as auth_router
from .routes.companies import router as companies_router
from .routes.reviews import router as reviews_router
from .routes.replies import router as replies_router
from .routes.dashboard import router as dashboard_router
from .routes.admin import router as admin_router
from .routes.reports import router as reports_router
from .routes.jobs import router as jobs_router
from .routes.alerts import router as alerts_router

app = FastAPI(title='Reputation Management SaaS')

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure runtime dirs exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static dirs
app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')
app.mount('/static', StaticFiles(directory='static'), name='static')

# Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Create DB tables
Base.metadata.create_all(bind=engine)

# Routers (API)
app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(reviews_router)
app.include_router(replies_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(jobs_router)
app.include_router(alerts_router)

# ---------- API root (JSON) ----------
@app.get('/')
async def root():
    return {"message": "Reputation SaaS API"}

# ---------- UI routes (HTML) ----------
# A simple landing page that points users to the dashboard
@app.get('/home')
async def home(request: Request):
    # You can render any landing page template here if you add it later.
    # For now, reuse dashboard layout with a minimal message.
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "content": "Welcome to Reputation SaaS. Go to /ui/dashboard/{company_id}."}
    )

# Render the dashboard HTML (uses templates/dashboard.html)
@app.get('/ui/dashboard/{company_id}')
async def dashboard_page(company_id: int, request: Request):
    # This template will call the JSON APIs from the browser to populate charts
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "company_id": company_id}
    )

# Optional: redirect '/' (JSON) to a UI page if you prefer
# Uncomment to redirect the root to /home or a specific dashboard
# @app.get('', include_in_schema=False)
# async def redirect_root():
#     return RedirectResponse(url='/home', status_code=307)

# Serve favicon if present; otherwise suppress 404 noise
@app.get('/favicon.ico')
async def favicon():
    path = os.path.join("static", "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/x-icon")
    return Response(status_code=204)

# HTTPS enforcement (prod)
@app.middleware("http")
async def https_enforce(request: Request, call_next):
    if HTTPS_ONLY and request.url.scheme != 'https':
        return Response('HTTPS required', status_code=400)
    return await call_next(request)
