# review_saas/app/main.py
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse  # NEW: to serve favicon when present
import os  # Added to create directories safely

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

# Ensure runtime directories exist (prevents mount errors in containers)
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)   # NEW: where favicon.ico can live

# Mount static & uploads
app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')
app.mount('/static', StaticFiles(directory='static'), name='static')  # NEW

# Create all database tables (if they don't exist)
Base.metadata.create_all(bind=engine)

# Include all API routers
app.include_router(auth_router)
app.include_router(companies_router)
app.include_router(reviews_router)
app.include_router(replies_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(jobs_router)
app.include_router(alerts_router)

@app.get('/')
async def root():
    return {"message": "Reputation SaaS API"}

# Serve favicon if present; otherwise return 204 to stop 404 noise
@app.get('/favicon.ico')
async def favicon():
    path = os.path.join("static", "favicon.ico")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/x-icon")
    return Response(status_code=204)  # No Content (silences 404s)

# Enforce HTTPS middleware (only active when HTTPS_ONLY is True)
@app.middleware("http")
async def https_enforce(request: Request, call_next):
    if HTTPS_ONLY and request.url.scheme != 'https':
        return Response('HTTPS required', status_code=400)
    return await call_next(request)
