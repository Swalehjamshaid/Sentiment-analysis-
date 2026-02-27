# filename: review_saas/app/main.py
from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session as SASession

from app.core.config import settings
from app.db import get_db, init_db
from app.routes import auth as auth_routes  # /register + login_post()

# New: include your feature routers
try:
    from app.routes import companies as companies_routes
except Exception:
    companies_routes = None  # soft-fallback

try:
    from app.routes import dashboard as dashboard_routes
except Exception:
    dashboard_routes = None  # soft-fallback

try:
    from app.routes import dashbord as dashbord_api  # REST API for dasbord.html
except Exception:
    dashbord_api = None  # soft-fallback

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

    # Provide globals used in your templates
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
        max_age=60 * 60 * 24 * 7,      # 7 days
    )

    # --------------------------
    # Include routers
    # --------------------------
    app.include_router(auth_routes.router)  # /register + POST /login helpers

    if companies_routes:
        app.include_router(companies_routes.router)  # /companies/create

    if dashboard_routes:
        app.include_router(dashboard_routes.router)  # SSR /dashboard route (your existing one)

    if dashbord_api:
        app.include_router(dashbord_api.router)      # /api/* endpoints used by dasbord.html

    # --------------------------
    # Helpers
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
        """
        Landing page renders base.html (Bootstrap modals for login/register).
        If already authenticated → redirect to dashboard.
        """
        if _is_authenticated(request):
            # Prefer your SSR dashboard route
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
        # Note: GET logout is convenient for your topbar anchor link.
        # For production security, consider POST with CSRF later.
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

    # Your existing SSR dashboard page remains intact via dashboard_routes.router.
    # Below: a *new* route to render the modern 'dashbord.html' (front-end that calls /api/*).
    @app.get("/dashbord", response_class=HTMLResponse)
    async def dashbord_page(request: Request):
        """
        Protected front-end page (Bootstrap+Chart.js) that consumes /api/* endpoints from routes/dashbord.py.
        Includes an 'Add Company' modal using Google Places Autocomplete.
        """
        user = _current_user(request)
        if not user:
            if "session" in request.scope:
                request.session["flash_error"] = "Please log in to continue."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        # Ensure CSRF for the Add Company form inside the template
        _ensure_csrf(request)

        # Pass Google Maps Places key for client-side autocomplete
        google_maps_api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "") or ""

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
    # Startup & Health
    # --------------------------
    @app.on_event("startup")
    async def on_startup():
        logger.info("Waiting for application startup.")
        try:
            init_db(drop_existing=False)
            logger.info("Database initialized successfully.")
            logger.info("User middleware: %s", [m.cls.__name__ for m in app.user_middleware])
        except Exception as e:
            logger.exception("Database init failed: %s", e)

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
