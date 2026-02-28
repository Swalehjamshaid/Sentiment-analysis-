# app/routers/__init__.py
from fastapi import APIRouter

from .auth import router as auth_router
from .company import router as company_router
from .review import router as review_router
from .sentiment import router as sentiment_router
from .replies import router as replies_router
from .dashboard import router as dashboard_router
from .reports import router as reports_router
from .admin import router as admin_router
from .alerts import router as alerts_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(company_router, prefix="/company", tags=["Company"])
api_router.include_router(review_router, prefix="/review", tags=["Reviews"])
api_router.include_router(sentiment_router, prefix="/sentiment", tags=["Sentiment"])
api_router.include_router(replies_router, prefix="/replies", tags=["Replies"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
