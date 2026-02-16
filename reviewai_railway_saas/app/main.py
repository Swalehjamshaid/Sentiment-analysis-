from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import time

from .database import engine, Base, settings
from .api import (
    auth as auth_api,
    companies as companies_api,
    reviews as reviews_api,
    reports as reports_api,
    admin as admin_api,
)

from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start background scheduler (e.g. for scheduled reports/jobs)
    scheduler.start()

    yield

    # Cleanup
    scheduler.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    # Optional: helps with some reverse-proxy setups on platforms like Railway
    root_path="/",
)


# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 templates
templates = Jinja2Templates(directory="app/templates")

# Include all API routers
app.include_router(auth_api.router)
app.include_router(companies_api.router)
app.include_router(reviews_api.router)
app.include_router(reports_api.router)
app.include_router(admin_api.router)


@app.get("/health", include_in_schema=False)  # Hide from OpenAPI docs if desired
async def health():
    """
    Simple health check endpoint for Railway (and monitoring).
    Returns 200 OK when the app is responsive.
    """
    # You can add real checks here later, e.g.:
    # - await check_db_connection()
    # - check_redis() if used
    # For now, just confirm the app is alive

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "app": settings.APP_NAME,
            "uptime_seconds": int(time.time() - app.state.get("start_time", time.time())),
        },
    )


# Optional: record start time for uptime calculation (set during lifespan startup if desired)
@app.on_event("startup")
async def record_start_time():
    app.state.start_time = time.time()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "app_name": settings.APP_NAME},
    )
