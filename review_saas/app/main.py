# filename: app/main.py

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from contextlib import suppress
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

# -------------------------------
# App internals (match your tree)
# -------------------------------
from app.core.config import settings  # Holds APP_NAME, DEBUG, SECRET_KEY, DB URLs/APIs
from app.core.db import engine        # SQLAlchemy engine (created in core/db.py)
from app.models.base import Base      # Declarative Base (defined in models/base.py)

# -------------------------------
# Optional: silence noisy warnings
# -------------------------------
with suppress(Exception):
    # Railway often prints a RequestsDependencyWarning; keep logs clean at runtime
    from requests.exceptions import RequestsDependencyWarning  # type: ignore[attr-defined]
    warnings.simplefilter("ignore", RequestsDependencyWarning)

# -------------------------------
# Logging
# -------------------------------
logger = logging.getLogger("review_saas")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
logger.info("Initializing application...")

# -------------------------------
# Paths
# -------------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# -------------------------------
# DB self-healing (otp_secret)
# -------------------------------
def _auto_patch_users_table() -> None:
    """
    If the 'users' table exists but lacks 'otp_secret', add it.
    This prevents 500s during register/login when the ORM model includes the column
    but the DB schema is missing it.
    """
    try:
        insp = inspect(engine)

        if "users" not in set(insp.get_table_names()):
            logger.info("Table 'users' not present yet; will be created by metadata.")
            return

        col_names = {c["name"] for c in insp.get_columns("users")}
        if "otp_secret" in col_names:
            logger.info("'users.otp_secret' exists; no schema patch needed.")
            return

        dialect = engine.dialect.name
        if dialect == "postgresql":
            ddl = "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_secret VARCHAR(64);"
        elif dialect == "sqlite":
            ddl = "ALTER TABLE users ADD COLUMN otp_secret TEXT;"
        else:
            ddl = "ALTER TABLE users ADD COLUMN otp_secret VARCHAR(64);"

        with engine.begin() as conn:
            conn.execute(text(ddl))

        logger.info("Schema patched: added column 'users.otp_secret'.")
    except SQLAlchemyError as e:
        logger.exception("DB schema self-heal step failed: %s", e)

# -------------------------------
# App factory
# -------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title=getattr(settings, "APP_NAME", "ReviewSaaS"),
                  debug=bool(getattr(settings, "DEBUG", False)))

    # Templates & static
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Sessions for simple email+password login (no JWT at this stage)
    app.add_middleware(SessionMiddleware, secret_key=getattr(settings, "SECRET_KEY", "change-me"))

    # ---------------------------
    # Middleware: Auth redirects
    # ---------------------------
    PROTECTED_PREFIXES = (
        "/dashboard",
        "/companies",
        "/reviews",
        "/reports",
        "/exports",
        "/admin",
    )

    @app.middleware("http")
    async def auth_redirects(request: Request, call_next):
        path = request.url.path
        authed = bool(request.session.get("user_id"))

        # Always allow static and health
        if path.startswith("/static") or path == "/health":
            return await call_next(request)

        # If logged in and visiting home/login/register -> send to dashboard
        if authed and path in ("/", "/login", "/register"):
            return RedirectResponse(url="/dashboard", status_code=302)

        # If not logged in and visiting protected areas -> send to login?next=
        if (not authed) and path.startswith(PROTECTED_PREFIXES):
            next_param = path
            if request.url.query:
                next_param += f"?{request.url.query}"
            return RedirectResponse(url=f"/login?next={quote(next_param, safe='')}", status_code=302)

        return await call_next(request)

    # ---------------------------
    # Routers (lazy import)
    # ---------------------------
    try:
        # Importing here avoids circular imports during app module import
        from app.routes import auth, dashboard, companies

        app.include_router(auth.router)                         # /login, /register, /logout
        app.include_router(dashboard.router)                    # /dashboard
        app.include_router(companies.router, prefix="/companies")  # /companies/*
    except Exception as e:
        logger.exception("Failed including routers: %s", e)

        @app.get("/__routers_error")
        def routers_error():
            return {"error": f"Routers failed to import: {e!r}"}

    # ---------------------------
    # Landing & health endpoints
    # ---------------------------
    @app.get("/")
    def index(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse(url="/dashboard", status_code=302)
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "env": getattr(settings, "ENVIRONMENT", "development"),
        }

    # ---------------------------
    # Startup hooks
    # ---------------------------
    @app.on_event("startup")
    def on_startup():
        logger.info("Initializing database...")
        # Create tables that don't exist yet
        Base.metadata.create_all(bind=engine)
        # Patch schema drift (otp_secret) if needed
        _auto_patch_users_table()

        # Start background scheduler (safe-guarded)
        with suppress(Exception):
            from app.services.scheduler import start_scheduler
            start_scheduler()
            logger.info("Background scheduler started.")
        logger.info("Application startup complete.")

    # ---------------------------
    # Graceful DB error handling
    # ---------------------------
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        msg = ("Database error. If this mentions 'UndefinedColumn users.otp_secret', "
               "restart once—startup self-heal adds the column automatically.")
        logger.exception("SQLAlchemyError: %s", exc)
        return JSONResponse({"detail": msg}, status_code=500)

    return app


# -------------------------------
# Create ASGI app
# -------------------------------
app = create_app()
