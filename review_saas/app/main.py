# filename: review_saas/app/main.py
from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.status import HTTP_302_FOUND
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session as SASession

# ─── Project imports ────────────────────────────────────────────────────────────
from app.core.config import settings
from app.db import get_db, init_db
from app.routes import auth as auth_routes  # contains register routes + login_post()

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("review_saas.main")

# ─── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    # Static & Templates (optional but helpful if you have them in the repo)
    base_dir = Path(__file__).parent
    static_dir = base_dir / "static"
    templates_dir = base_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates: Optional[Jinja2Templates] = None
    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

    # CORS (adjust for your environment as needed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Sessions (REQUIRED for request.session to persist)
    # Note: For local dev over http, https_only=False is fine.
    # Behind a proxy with TLS, set FORCE_HTTPS=1 and pass proxy headers.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        same_site="lax",
        https_only=bool(settings.FORCE_HTTPS),
        session_cookie="sessionid",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )

    # ── Optional: Redirect plain HTTP to HTTPS when FORCE_HTTPS=1 ──────────────
    if int(getattr(settings, "FORCE_HTTPS", 0)) == 1:
        @app.middleware("http")
        async def force_https_redirect(request: Request, call_next):
            # Trust reverse proxy header if present
            forwarded_proto = request.headers.get("x-forwarded-proto")
            scheme = forwarded_proto or request.url.scheme
            if scheme != "https":
                url = request.url.replace(scheme="https")
                return RedirectResponse(url=str(url), status_code=HTTP_302_FOUND)
            return await call_next(request)

    # ── Ensure CSRF token exists in session for forms (register uses it) ───────
    @app.middleware("http")
    async def ensure_csrf(request: Request, call_next):
        # Make sure session exists before reading/writing
        _ = request.session  # touch to initialize
        if "_csrf" not in request.session:
            # urlsafe token so it’s safe to embed in HTML
            request.session["_csrf"] = secrets.token_urlsafe(32)
        response: Response = await call_next(request)
        return response

    # ─── Include routers (Register endpoints live here) ────────────────────────
    app.include_router(auth_routes.router)

    # ─── Views ────────────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """
        Basic home. If you have templates/base.html that shows the login/register
        modal depending on ?show=login|register, this will render it.
        Otherwise, it falls back to a minimal HTML response.
        """
        show = request.query_params.get("show")
        ctx = {
            "request": request,
            "show": show,
            "user_id": request.session.get("user_id"),
            "user_name": request.session.get("user_name"),
            "csrf_token": request.session.get("_csrf"),
            "flash_error": request.session.pop("flash_error", None),
            "flash_success": request.session.pop("flash_success", None),
        }

        if templates:  # render templates/base.html if available
            try:
                return templates.TemplateResponse("base.html", ctx)
            except Exception as e:
                logger.warning("Template render failed: %s", e)

        # Fallback minimal HTML (no templates found)
        return HTMLResponse(
            f"""
            <html>
            <head><title>{settings.APP_NAME}</title></head>
            <body style="font-family: system-ui, sans-serif;">
                <h2>{settings.APP_NAME}</h2>
                <p>Session user: {ctx['user_name'] or 'anonymous'}</p>
                <p>Flash (error): {ctx['flash_error'] or '-'}</p>
                <p>Flash (success): {ctx['flash_success'] or '-'}</p>
                <p>CSRF: {ctx['csrf_token'][:6]}…</p>
                <hr />
                <form method="post" action="/login">
                    <input type="email" name="email" placeholder="email" required />
                    <input type="password" name="password" placeholder="password" required />
                    <button type="submit">Login</button>
                </form>
                <p>Or <a href="/?show=register">register</a></p>
            </body>
            </html>
            """,
            status_code=200,
        )

    # ─── Login/Logout Routes ──────────────────────────────────────────────────
    @app.get("/login")
    async def login_view():
        # Defer to base.html to open the Login modal via ?show=login
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    @app.post("/login")
    async def login_handler(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: SASession = Depends(get_db),
    ):
        """
        Invokes the helper in app/routes/auth.py:
        async def login_post(request: Request, email: str, password: str, db: Session) -> Optional[User]
        """
        # Call your existing login helper
        user = await auth_routes.login_post(
            request=request, email=email, password=password, db=db
        )

        if not user:
            request.session["flash_error"] = "Invalid email or password."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        # ✅ Mark session as authenticated
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email
        request.session["user_name"] = user.full_name
        request.session["flash_success"] = "Welcome back!"

        return RedirectResponse("/", status_code=HTTP_302_FOUND)

    @app.post("/logout")
    async def logout(request: Request):
        request.session.clear()
        # Regenerate CSRF for next session
        request.session["_csrf"] = secrets.token_urlsafe(32)
        request.session["flash_success"] = "Signed out."
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    # ─── Start-up & Health ────────────────────────────────────────────────────
    @app.on_event("startup")
    async def on_startup():
        logger.info("Waiting for application startup.")
        try:
            init_db(drop_existing=False)
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.exception("Database init failed: %s", e)
            # Do not crash; allow app to boot so you can see logs

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app


# ─── Uvicorn entrypoint ────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,          # turn off in production
        proxy_headers=True,   # trust X-Forwarded-* from reverse proxy
    )
