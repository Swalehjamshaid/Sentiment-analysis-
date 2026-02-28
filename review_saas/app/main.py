# filename: app/main.py
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import logging

from .core.config import settings
from .db import init_db_sync
from .models import Base
from .routers import auth as auth_router
from .routers import companies as companies_router
from .routers import dashboard as dashboard_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

app = FastAPI(title="ReviewSaaS")
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET)

app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
def startup():
    logger.info('Initializing database...')
    init_db_sync(Base)

@app.get('/')
def index(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})

app.include_router(auth_router.router)
app.include_router(companies_router.router)
app.include_router(dashboard_router.router)
