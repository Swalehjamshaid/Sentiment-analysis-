
# filename: app/main.py
from __future__ import annotations
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from .core.settings import settings
from .core.db import init_db
from .models.base import Base
from .routes import auth, companies, reviews, dashboard, exports, reports, admin
from .services.scheduler import start_scheduler
from .core.db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('review_saas')

app = FastAPI(title=settings.APP_NAME)

templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
def on_start():
    logger.info('Initializing database...')
    init_db(Base)
    start_scheduler()

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', { 'request': request, 'title': settings.APP_NAME })

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(reviews.router)
app.include_router(dashboard.router)
app.include_router(exports.router)
app.include_router(reports.router)
app.include_router(admin.router)
