# filename: review_saas/app/main.py
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND

from sqlalchemy.orm import Session as SASession

from app.core.config import settings
from app.db import get_db, init_db
from app.routes import auth as auth_routes

# Optional routers
try:
    from app.routes import companies as companies_routes
except Exception:
    companies_routes = None

try:
    from app.routes import dashbord as dashbord_api
except Exception:
    dashbord_api = None

# Optional services
try:
    from app.services.google_api import get_google_api_service
except Exception:
    get_google_api_service = None

try:
    import googlemaps
except Exception:
    googlemaps = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("review_saas.main")

def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    # --------------------------
    # Templates & Static
    # --------------------------
    base_dir = Path(__file__).parent
    templates_dir = base_dir / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    templates.env.globals["now"] = lambda: datetime.now()
    templates.env.globals["app_name"] = settings.APP_NAME

    static_dir = base_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # --------------------------
    # Middleware
    # --------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        same_site="lax",
        https_only=bool(settings.FORCE_HTTPS),
        session_cookie="sessionid",
        max_age=60 * 60 * 24 * 7,
    )

    # --------------------------
    # Routers
    # --------------------------
    app.include_router(auth_routes.router)

    if companies_routes:
        app.include_router(companies_routes.router)

    if dashbord_api:
        # We include this without an extra prefix because dashbord_api.router 
        # already defines prefix="/api"
        app.include_router(dashbord_api.router)

    # --------------------------
    # Auth Helpers
    # --------------------------
    def _ensure_csrf(request: Request) -> Optional[str]:
        if "session" not in request.scope:
            return None
        if request.session.get("_csrf") is None:
            request.session["_csrf"] = secrets.token_urlsafe(32)
        return request.session.get("_csrf")

    def _current_user(request: Request):
        if "session" in request.scope and request.session.get("user_id"):
            return {
                "id": request.session.get("user_id"),
                "full_name": request.session.get("user_name"),
                "email": request.session.get("user_email"),
            }
        return None

    def _is_authenticated(request: Request) -> bool:
        return _current_user(request) is not None

    # --------------------------
    # Views
    # --------------------------
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        if _is_authenticated(request):
            return RedirectResponse("/dashboard", status_code=HTTP_302_FOUND)
        
        csrf_token = _ensure_csrf(request)
        show = request.query_params.get("show") or "login"
        ctx = {
            "request": request,
            "app_name": settings.APP_NAME,
            "show": show,
            "csrf_token": csrf_token,
            "flash_error": request.session.pop("flash_error", None) if "session" in request.scope else None,
            "flash_success": request.session.pop("flash_success", None) if "session" in request.scope else None,
            "current_user": _current_user(request),
        }
        return templates.TemplateResponse("base.html", ctx)

    @app.get("/login")
    async def login_view(request: Request):
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    @app.post("/login")
    async def login_handler(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: SASession = Depends(get_db),
    ):
        user = await auth_routes.login_post(request=request, email=email, password=password, db=db)
        if not user:
            if "session" in request.scope:
                request.session["flash_error"] = "Invalid email or password."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        if "session" in request.scope:
            request.session["user_id"] = user.id
            request.session["user_email"] = user.email
            request.session["user_name"] = user.full_name
            request.session["flash_success"] = "Welcome back!"
        return RedirectResponse("/dashboard", status_code=HTTP_302_FOUND)

    @app.get("/logout")
    async def logout_get(request: Request):
        if "session" in request.scope:
            request.session.clear()
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    # --------------------------
    # Unified Dashboard
    # --------------------------
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page(request: Request):
        """
        Unified Dashboard route. Renders dashbord.html which 
        uses the /api/* endpoints for data.
        """
        user = _current_user(request)
        if not user:
            if "session" in request.scope:
                request.session["flash_error"] = "Please log in to continue."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        _ensure_csrf(request)

        # Ensure we pull the key from environment for the template
        google_maps_api_key = (
            getattr(settings, "GOOGLE_MAPS_API_KEY", None)
            or os.getenv("GOOGLE_MAPS_API_KEY", "")
        )

        ctx = {
            "request": request,
            "app_name": settings.APP_NAME,
            "current_user": user,
            "google_maps_api_key": google_maps_api_key,
            "flash_error": request.session.pop("flash_error", None) if "session" in request.scope else None,
            "flash_success": request.session.pop("flash_success", None) if "session" in request.scope else None,
        }
        return templates.TemplateResponse("dashbord.html", ctx)

    # --------------------------
    # Lifecycle & Health
    # --------------------------
    @app.on_event("startup")
    async def on_startup():
        init_db(drop_existing=False)
        
        places_key = getattr(settings, "GOOGLE_PLACES_API_KEY", None) or os.getenv("GOOGLE_PLACES_API_KEY")
        if places_key and googlemaps:
            app.state.gmaps = googlemaps.Client(key=places_key)
            logger.info("Google Places client initialized.")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app

app = create_app()
