from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.gzip import GZipMiddleware
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
    from app.services.google_api import get_google_api_service  # noqa: F401
except Exception:
    get_google_api_service = None  # type: ignore

try:
    import googlemaps  # type: ignore
except Exception:
    googlemaps = None  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("review_saas.main")


# --------------------------
# Security Headers Middleware (non-breaking defaults)
# --------------------------
async def _add_security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
        # Safe, common headers that should not break existing behavior
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer-when-downgrade")
        # Light cache policy for dynamic HTML; keeps assets behavior unchanged
        if response.media_type in ("text/html", "application/xhtml+xml"):
            response.headers.setdefault("Cache-Control", "private, no-store, max-age=0")
        return response
    except Exception as e:
        logger.exception("Error in security headers middleware: %s", e)
        raise e


def _get_allowed_hosts():
    hosts = getattr(settings, "ALLOWED_HOSTS", None)
    if hosts and isinstance(hosts, (list, tuple)) and len(hosts) > 0:
        return list(hosts)
    return ["*"]


def _get_google_keys():
    maps_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None) or os.getenv("GOOGLE_MAPS_API_KEY")
    places_key = getattr(settings, "GOOGLE_PLACES_API_KEY", None) or os.getenv("GOOGLE_PLACES_API_KEY")
    return maps_key, places_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(drop_existing=False)

    _maps_key, places_key = _get_google_keys()
    if places_key and googlemaps:
        try:
            app.state.gmaps = googlemaps.Client(key=places_key)
            logger.info("Google Places client initialized.")
        except Exception as e:
            logger.warning("Failed to initialize Google Places client: %s", e)
    else:
        logger.info("Google Places client not initialized (missing key or library).")

    yield

    if hasattr(app.state, "gmaps"):
        # No explicit cleanup needed; GC will handle it
        pass


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

    # --------------------------
    # Templates & Static
    # --------------------------
    base_dir = Path(__file__).parent
    templates_dir = base_dir / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    # Global helpers
    templates.env.globals["now"] = lambda: datetime.now()
    templates.env.globals["app_name"] = settings.APP_NAME

    static_dir = base_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    else:
        logger.info("Static directory not found at %s; skipping static mount.", static_dir)

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
        TrustedHostMiddleware,
        allowed_hosts=_get_allowed_hosts(),
    )

    app.add_middleware(
        GZipMiddleware,
        minimum_size=1024,
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        same_site="lax",
        https_only=bool(getattr(settings, "FORCE_HTTPS", False)),
        session_cookie="sessionid",
        max_age=60 * 60 * 24 * 7,
    )

    app.middleware("http")(_add_security_headers)

    # --------------------------
    # Routers
    # --------------------------
    app.include_router(auth_routes.router)

    if companies_routes:
        app.include_router(companies_routes.router)

    if dashbord_api:
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

   
