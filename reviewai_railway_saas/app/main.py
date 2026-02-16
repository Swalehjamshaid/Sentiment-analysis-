from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from .database import engine, Base, settings
from .api import auth as auth_api, companies as companies_api, reviews as reviews_api, reports as reports_api, admin as admin_api

from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # start scheduler
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_api.router)
app.include_router(companies_api.router)
app.include_router(reviews_api.router)
app.include_router(reports_api.router)
app.include_router(admin_api.router)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "app_name": settings.APP_NAME})