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
from app.routes import auth as auth_routes  # /register + login_post()

# Optional routers (soft-import to avoid crashes during early wiring)
try:
    from app.routes import companies as companies_routes  # /companies/create
except Exception:
    companies_routes = None  # soft fallback

try:
    from app.routes import dashbord as dashbord_api  # /api/* endpoints for dashbord.html
except Exception:
    dashbord_api = None  # soft fallback

# Optional: Google Business API (service account)
try:
    from app.services.google_api import get_google_api_service
except Exception:
    get_google_api_service = None  # soft fallback

# Optional: googlemaps (Places REST client)
try:
    import googlemaps  # type: ignore
except Exception:
    googlemaps = None  # soft fallback

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

    # Provide globals used in templates
    templates.env.globals["now"] = lambda: datetime.now()
    templates.env.globals["app_name"] = settings.APP_NAME

    # Optional: mount /static if present
    static_dir = base_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # --------------------------
    # CORS
    # --------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],            # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------
    # Sessions (CSRF-capable)
    # --------------------------
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        same_site="lax",
        https_only=bool(settings.FORCE_HTTPS),
        session_cookie="sessionid",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )

    # --------------------------
    # Routers
    # --------------------------
    app.include_router(auth_routes.router)  # /register, POST /login helpers

    if companies_routes:
        app.include_router(companies_routes.router)  # /companies/create

    if dashbord_api:
        app.include_router(dashbord_api.router)  # /api/* endpoints used by dasbord.html

    # --------------------------
    # Helpers (session, auth)
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
    # Views (public/auth)
    # --------------------------
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """
        Landing page renders base.html (Bootstrap modals for login/register).
        If already authenticated → redirect to /dashboard.
        """
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
        if _is_authenticated(request):
            return RedirectResponse("/dashboard", status_code=HTTP_302_FOUND)
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

        # Go to dashboard after successful login
        return RedirectResponse("/dashboard", status_code=HTTP_302_FOUND)

    @app.get("/logout")
    async def logout_get(request: Request):
        # For convenience in topbar links. Consider POST+CSRF for production hardening.
        if "session" in request.scope:
            request.session.clear()
            request.session["_csrf"] = secrets.token_urlsafe(32)
            request.session["flash_success"] = "Signed out."
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    @app.post("/logout")
    async def logout_post(request: Request):
        if "session" in request.scope:
            request.session.clear()
            request.session["_csrf"] = secrets.token_urlsafe(32)
            request.session["flash_success"] = "Signed out."
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    # --------------------------
    # SSR Dashboard (kept in main.py to avoid route conflicts)
    # --------------------------
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """
        Protected page. If not authenticated → redirect to login.
        Renders templates/dashboard.html (your SSR page).
        """
        user = _current_user(request)
        if not user:
            if "session" in request.scope:
                request.session["flash_error"] = "Please log in to continue."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        ctx = {
            "request": request,
            "app_name": settings.APP_NAME,
            "current_user": user,
            "flash_error": request.session.pop("flash_error", None),
            "flash_success": request.session.pop("flash_success", None),
        }
        return templates.TemplateResponse("dashboard.html", ctx)

    # --------------------------
    # Modern Front-end Dashboard (calls /api/*)
    # --------------------------
    @app.get("/dashbord", response_class=HTMLResponse)
    async def dashbord_page(request: Request):
        """
        Protected front-end page (Bootstrap+Chart.js) that consumes /api/* endpoints.
        Includes an 'Add Company' modal using Google Places Autocomplete.
        Renders templates/dashbord.html
        """
        user = _current_user(request)
        if not user:
            if "session" in request.scope:
                request.session["flash_error"] = "Please log in to continue."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        # Ensure CSRF for the Add Company form inside the template
        _ensure_csrf(request)

        # Pass Google Maps Places API key for client-side autocomplete
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
    # Google Health (keys & initialization status)
    # --------------------------
    @app.get("/google/health")
    async def google_health():
        maps_js_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None) or os.getenv("GOOGLE_MAPS_API_KEY")
        places_key = getattr(settings, "GOOGLE_PLACES_API_KEY", None) or os.getenv("GOOGLE_PLACES_API_KEY")
        creds_path = (
            getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None)
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or os.getenv("GOOGLE_CREDENTIALS_JSON")
        )
        return {
            "maps_js_client": bool(maps_js_key),
            "places_rest_server": bool(places_key),
            "business_creds_path": creds_path if creds_path else None,
            "server_places_client_initialized": bool(getattr(app.state, "gmaps", None)),
            "business_service_initialized": bool(getattr(app.state, "google_business", None)),
        }

    # --------------------------
    # Startup & Health
    # --------------------------
    @app.on_event("startup")
    async def on_startup():
        logger.info("Waiting for application startup.")
        try:
            # Initialize DB
            init_db(drop_existing=False)
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.exception("Database init failed: %s", e)

        # --- Google Places (server-side) ---
        try:
            places_key = (
                getattr(settings, "GOOGLE_PLACES_API_KEY", None)
                or os.getenv("GOOGLE_PLACES_API_KEY")
            )
            if places_key and googlemaps is not None:
                app.state.gmaps = googlemaps.Client(key=places_key)
                logger.info("Google Places (REST) client initialized.")
            else:
                app.state.gmaps = None
                if not places_key:
                    logger.warning("GOOGLE_PLACES_API_KEY not set. Server-side Places client disabled.")
                if googlemaps is None:
                    logger.warning("python-googlemaps not installed. Server-side Places client disabled.")
        except Exception as e:
            app.state.gmaps = None
            logger.warning("Google Places client initialization failed: %s", e)

        # --- Google Business API (service account) ---
        try:
            # get_google_api_service reads GOOGLE_APPLICATION_CREDENTIALS or provided path
            if get_google_api_service is not None:
                creds_path = (
                    getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None)
                    or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                    or os.getenv("GOOGLE_CREDENTIALS_JSON")
                )
                if creds_path:
                    app.state.google_business = get_google_api_service(credentials_json_path=creds_path)
                    # The service object is internal; presence indicates init success
                    logger.info("Google Business API service attempted with credentials at %s", creds_path)
                else:
                    app.state.google_business = None
                    logger.warning("Google Business credentials path not set. Business API disabled.")
            else:
                app.state.google_business = None
                logger.warning("get_google_api_service not available. Business API disabled.")
        except Exception as e:
            app.state.google_business = None
            logger.warning("Google Business API init failed: %s", e)

        logger.info("User middleware: %s", [m.cls.__name__ for m in app.user_middleware])

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        proxy_headers=True,
    )
