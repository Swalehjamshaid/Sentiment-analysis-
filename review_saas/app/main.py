# filename: app/main.py
from __future__ import annotations

import logging
import warnings
from pathlib import Path
from contextlib import suppress, asynccontextmanager
from urllib.parse import quote

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
from app.core.config import settings
from app.core.db import engine
from app.models.base import Base

# -------------------------------
# Optional: silence noisy warnings
# -------------------------------
with suppress(Exception):
    from requests.exceptions import RequestsDependencyWarning
    warnings.simplefilter("ignore", RequestsDependencyWarning)

# -------------------------------
# Logging Configuration
# -------------------------------
logger = logging.getLogger("review_saas")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# -------------------------------
# DB self-healing logic
# -------------------------------
def _auto_patch_users_table() -> None:
    """Requirement 124: Ensures schema consistency without manual migrations."""
    try:
        insp = inspect(engine)
        if "users" not in set(insp.get_table_names()):
            logger.info("Table 'users' not present yet; skipping patch.")
            return

        col_names = {c["name"] for c in insp.get_columns("users")}
        if "otp_secret" in col_names:
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
    except Exception as e:
        logger.warning(f"DB schema self-heal step skipped: {e}")

# -------------------------------
# Modern Lifespan Manager
# -------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Initializing application startup...")
    try:
        # Create tables from models
        import app.models.models
        Base.metadata.create_all(bind=engine)
        
        # Patch schema for existing databases
        _auto_patch_users_table()

        # Start background scheduler
        with suppress(Exception):
            from app.services.scheduler import start_scheduler
            start_scheduler()
            logger.info("Background scheduler started.")
            
        logger.info("Application startup complete.")
    except Exception as e:
        logger.error(f"Critical error during startup: {e}")
    
    yield
    
    # --- Shutdown ---
    logger.info("Shutting down application...")

# -------------------------------
# App factory
# -------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title=getattr(settings, "APP_NAME", "ReviewSaaS"),
        debug=bool(getattr(settings, "DEBUG", False)),
        lifespan=lifespan
    )

    # Paths Setup
    BASE_DIR = Path(__file__).resolve().parent
    TEMPLATES_DIR = BASE_DIR / "templates"
    STATIC_DIR = BASE_DIR / "static"

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Session Middleware
    app.add_middleware(
        SessionMiddleware, 
        secret_key=getattr(settings, "SECRET_KEY", "change-me"),
        https_only=not bool(getattr(settings, "DEBUG", False)),
        same_site="lax"
    )

    # Authentication & Redirect Middleware
    PROTECTED_PREFIXES = ("/dashboard", "/companies", "/reviews", "/reports", "/exports", "/admin")

    @app.middleware("http")
    async def auth_redirect_middleware(request: Request, call_next):
        path = request.url.path
        is_authenticated = bool(request.session.get("user_id"))

        # Bypass for static and health checks
        if path.startswith("/static") or path == "/health":
            return await call_next(request)

        # Redirect logged-in users away from landing/auth pages
        if is_authenticated and path in ("/", "/login", "/register"):
            return RedirectResponse(url="/dashboard", status_code=302)

        # Protect dashboard and management areas
        if not is_authenticated and path.startswith(PROTECTED_PREFIXES):
            next_param = quote(path + (f"?{request.url.query}" if request.url.query else ""), safe="")
            return RedirectResponse(url=f"/login?next={next_param}", status_code=302)

        return await call_next(request)

    # Router Registration
    try:
        from app.routes import auth, dashboard, companies
        app.include_router(auth.router)
        app.include_router(dashboard.router)
        app.include_router(companies.router, prefix="/companies")
    except Exception as e:
        logger.error(f"Failed to include routers: {e}")

    # Core Endpoints
    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "database": engine.dialect.name,
            "environment": getattr(settings, "ENVIRONMENT", "development")
        }

    # Global Exception Handlers
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        logger.exception(f"Database Error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "A database error occurred. Please refresh or contact support."}
        )

    return app

# -------------------------------
# Create ASGI app
# -------------------------------
app = create_app()
