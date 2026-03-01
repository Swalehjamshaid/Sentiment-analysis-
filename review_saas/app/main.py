# File: app/main.py

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

# -------------------------------
# App internals
# -------------------------------
from app.core.config import settings  # FIXED import
from app.core.db import Base, engine

# Optional: quiet the 'RequestsDependencyWarning' noise at runtime
with suppress(Exception):
    from requests.exceptions import RequestsDependencyWarning  # type: ignore
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
# DB self-healing
# -------------------------------
def _auto_patch_users_table(engine) -> None:
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
                ddl = "ALTER TABLE users ADD COLUMN otp_secret TEXT;"
            else:
                ddl = "ALTER TABLE users ADD COLUMN otp_secret VARCHAR(64);"

            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("Schema patched: added 'users.otp_secret' column.")
        else:
            logger.info("'users.otp_secret' already present; no patch needed.")

    except SQLAlchemyError as e:
        logger.exception("DB schema self-heal step failed: %s", e)

# -------------------------------
# App factory
# -------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=getattr(settings, "DEBUG", False))

    # Templates & static
    TEMPLATES_DIR.mkdir(exist_ok=True, parents=True)
    STATIC_DIR.mkdir(exist_ok=True, parents=True)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Sessions for login state
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

    # -------------------------------
    # Middleware: Auth redirects
    # -------------------------------
    PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

    @app.middleware("http")
    async def auth_redirects(request: Request, call_next):
        path = request.url.path
        authed = bool(request.session.get("user_id"))

        # Allow static files and health checks
        if path.startswith("/static") or path == "/health":
            return await call_next(request)

        # Redirect logged-in users away from login/register/home
        if authed and path in ("/", "/login", "/register"):
            return RedirectResponse("/dashboard")

        # Redirect unauthenticated users from protected paths
        if not authed and path.startswith(PROTECTED_PREFIXES):
            next_param = request.url.path
            if request.url.query:
                next_param += f"?{request.url.query}"
            from urllib.parse import quote
            next_param = quote(next_param, safe="")
            return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

        return await call_next(request)

    # -------------------------------
    # Routers (lazy import)
    # -------------------------------
    try:
        from app.routes import auth, dashboard, companies
        app.include_router(auth.router)
        app.include_router(dashboard.router)
        app.include_router(companies.router, prefix="/companies")
    except Exception as e:
        logger.exception("Failed including routers: %s", e)
        @app.get("/__routers_error")
        def routers_error():
            return {"error": f"Routers failed to import: {e!r}"}

    # -------------------------------
    # Landing & health
    # -------------------------------
    @app.get("/")
    def index(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse(url="/dashboard")
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health")
    def health():
        return {"status": "ok", "env": getattr(settings, "ENVIRONMENT", "dev")}

    # -------------------------------
    # Startup: DB init + self-heal + scheduler
    # -------------------------------
    @app.on_event("startup")
    def on_startup():
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        _auto_patch_users_table(engine)

        with suppress(Exception):
            from app.services.scheduler import start_scheduler
            start_scheduler()
            logger.info("Background scheduler started.")

        logger.info("Application startup complete.")

    # -------------------------------
    # Graceful error handling
    # -------------------------------
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        msg = "Database error. If this is 'UndefinedColumn users.otp_secret', restart the app; schema self-heal will add it."
        logger.exception("SQLAlchemyError: %s", exc)
        return JSONResponse({"detail": msg}, status_code=500)

    return app

# -------------------------------
# Create ASGI app
# -------------------------------
app = create_app()
