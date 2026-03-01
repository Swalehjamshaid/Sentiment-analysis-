# filename: app/app/main.py
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, JSONResponse

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

# App internals (one-way imports to avoid circulars)
from app.core.settings import settings
from app.core.db import Base, engine

# Optional: quiet the 'RequestsDependencyWarning' noise at runtime
with suppress(Exception):
    from requests.exceptions import RequestsDependencyWarning  # type: ignore
    warnings.simplefilter("ignore", RequestsDependencyWarning)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger("review_saas")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
logger.info("Initializing application...")

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# -----------------------------------------------------------------------------
# DB self-healing (adds missing columns we care about)
# -----------------------------------------------------------------------------
def _auto_patch_users_table(engine) -> None:
    """
    Ensure the 'users' table has the columns the ORM expects.
    Currently patches: otp_secret (String(64), nullable=True)

    Safe to run on every startup:
      - Uses SQLAlchemy inspector to only apply when actually missing.
      - Uses dialect-aware DDL for Postgres/SQLite.
    """
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "users" not in tables:
            logger.info("Table 'users' not found yet; will be created by metadata.")
            return

        columns = {c["name"] for c in insp.get_columns("users")}
        if "otp_secret" not in columns:
            dialect = engine.dialect.name
            if dialect == "postgresql":
                ddl = "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_secret VARCHAR(64);"
            elif dialect == "sqlite":
                # SQLite lacks IF NOT EXISTS for ADD COLUMN, but we already checked it's missing
                ddl = "ALTER TABLE users ADD COLUMN otp_secret TEXT;"
            else:
                # Generic fallback: most SQL dialects accept VARCHAR(64)
                ddl = "ALTER TABLE users ADD COLUMN otp_secret VARCHAR(64);"

            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("Schema patched: added 'users.otp_secret' column.")
        else:
            logger.info("'users.otp_secret' already present; no patch needed.")

    except SQLAlchemyError as e:
        # Do not crash startup—log and continue so app remains responsive
        logger.exception("DB schema self-heal step failed: %s", e)


# -----------------------------------------------------------------------------
# App factory
# -----------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    # Templates & static
    TEMPLATES_DIR.mkdir(exist_ok=True, parents=True)
    STATIC_DIR.mkdir(exist_ok=True, parents=True)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Sessions for login state
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    # -------------------------------------------------------------------------
    # Middleware: When already authenticated, keep flows tidy
    # Visiting "/", "/login", "/register" → redirect to "/dashboard"
    # -------------------------------------------------------------------------
    @app.middleware("http")
    async def auth_redirects(request: Request, call_next):
        path = request.url.path
        if request.session.get("user_id") and path in ("/", "/login", "/register"):
            return RedirectResponse(url="/dashboard")
        return await call_next(request)

    # -------------------------------------------------------------------------
    # Routers (import lazily to avoid accidental circulars)
    # -------------------------------------------------------------------------
    try:
        from app.routes import auth, dashboard  # noqa
        app.include_router(auth.router)
        app.include_router(dashboard.router)
    except Exception as e:
        logger.exception("Failed including routers: %s", e)
        # Keep app booting; surface the problem at /health
        @app.get("/__routers_error")
        def routers_error():
            return {"error": f"Routers failed to import: {e!r}"}

    # -------------------------------------------------------------------------
    # Landing & health
    # -------------------------------------------------------------------------
    @app.get("/")
    def index(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse(url="/dashboard")
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health")
    def health():
        return {"status": "ok", "env": settings.environment}

    # -------------------------------------------------------------------------
    # Startup: create tables (idempotent) then run self-healing schema patch
    # -------------------------------------------------------------------------
    @app.on_event("startup")
    def on_startup():
        logger.info("Initializing database...")
        # Create tables that don't exist (does not add columns to existing tables)
        Base.metadata.create_all(bind=engine)
        # Patch missing columns we depend on (e.g., users.otp_secret)
        _auto_patch_users_table(engine)
        # Optionally start background scheduler if present (keeps flexible)
        with suppress(Exception):
            from app.scheduler import start_scheduler  # optional module
            start_scheduler()
            logger.info("Background scheduler started.")

        logger.info("Application startup complete.")

    # -------------------------------------------------------------------------
    # Graceful error surface for DB column mismatch (extra safety)
    # -------------------------------------------------------------------------
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        # If something slips past the self-heal, return a meaningful message
        msg = "Database error. If this is 'UndefinedColumn users.otp_secret', restart the app; the schema self-heal will add it automatically."
        logger.exception("SQLAlchemyError: %s", exc)
        return JSONResponse({"detail": msg}, status_code=500)

    return app


# -----------------------------------------------------------------------------
# Create the ASGI app
# -----------------------------------------------------------------------------
app = create_app()
