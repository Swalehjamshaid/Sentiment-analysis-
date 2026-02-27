# filename: app/app/main.py
import os, logging
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.db import engine, Base
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.companies import router as companies_router
from app.routes.exports import router as exports_router
from app.routes.google_routes import router as google_router

logger = logging.getLogger('review_saas.main')
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=get_settings().app_name)
app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)

os.makedirs('static', exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')

templates = Jinja2Templates(directory='templates')

@app.on_event('startup')
async def on_startup():
    logging.getLogger('app.db').info('Ensuring tables exist...')
    Base.metadata.create_all(bind=engine)
    logging.getLogger('app.db').info('Database sync complete.')
    from app.services.google_api import _ensure_client
    client = _ensure_client()
    if client:
        logger.info('Google Places client initialized.')

@app.get('/', include_in_schema=False)
async def root(request: Request):
    if request.session.get('user'):
        return RedirectResponse('/dashboard?show=dashboard', status_code=302)
    return RedirectResponse('/dashboard?show=login', status_code=302)

@app.get('/dashboard', include_in_schema=False)
async def dashboard_view(request: Request):
    return templates.TemplateResponse('dashboard.html', { 'request': request, 'google_maps_api_key': get_settings().google_maps_api_key or get_settings().google_places_api_key })

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    path = os.path.join('static', 'favicon.ico')
    if os.path.exists(path):
        return FileResponse(path)
    return Response(status_code=404)

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(companies_router)
app.include_router(exports_router)
app.include_router(google_router)
