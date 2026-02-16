
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import ALLOWED_ORIGINS
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

app.mount('/uploads', StaticFiles(directory='uploads'), name='uploads')

Base.metadata.create_all(bind=engine)

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

from fastapi import Request, Response
from .config import HTTPS_ONLY
@app.middleware("http")
async def https_enforce(request: Request, call_next):
    if HTTPS_ONLY and request.url.scheme != 'https':
        return Response('HTTPS required', status_code=400)
    return await call_next(request)
