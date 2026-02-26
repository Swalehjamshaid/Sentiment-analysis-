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

from app.core.config import settings
from app.db import get_db, init_db
from app.routes import auth as auth_routes  # register routes + login_post()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("review_saas.main")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)

    # Static & Templates (optional)
    base_dir = Path(__file__).parent
    static_dir = base_dir / "static"
    templates_dir = base_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates: Optional[Jinja2Templates] = None
    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Sessions (REQUIRED)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        same_site="lax",
        https_only=bool(settings.FORCE_HTTPS),
        session_cookie="sessionid",
        max_age=60 * 60 * 24 * 7,    # 7 days
    )

    # Optional: Force HTTPS (behind a proxy set FORCE_HTTPS=1 and pass proxy headers)
    if int(getattr(settings, "FORCE_HTTPS", 0)) == 1:
        @app.middleware("http")
        async def force_https_redirect(request: Request, call_next):
            forwarded_proto = request.headers.get("x-forwarded-proto")
            scheme = forwarded_proto or request.url.scheme
            if scheme != "https":
                url = request.url.replace(scheme="https")
                return RedirectResponse(url=str(url), status_code=HTTP_302_FOUND)
            return await call_next(request)

    # ✅ SAFE ensure_csrf: do not assume session exists
    @app.middleware("http")
    async def ensure_csrf(request: Request, call_next):
        if "session" in request.scope:
            session = request.session
            if session.get("_csrf") is None:
                session["_csrf"] = secrets.token_urlsafe(32)
        response: Response = await call_next(request)
        return response

    # Routers (Register endpoints live here)
    app.include_router(auth_routes.router)

    # Home
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        show = request.query_params.get("show")
        ctx = {
            "request": request,
            "show": show,
            "user_id": request.session.get("user_id") if "session" in request.scope else None,
            "user_name": request.session.get("user_name") if "session" in request.scope else None,
            "csrf_token": request.session.get("_csrf") if "session" in request.scope else None,
            "flash_error": request.session.pop("flash_error", None) if "session" in request.scope else None,
            "flash_success": request.session.pop("flash_success", None) if "session" in request.scope else None,
        }

        if templates:
            try:
                return templates.TemplateResponse("base.html", ctx)
            except Exception as e:
                logger.warning("Template render failed: %s", e)

        # Fallback minimal HTML if you don't have templates/base.html
        csrf_preview = (ctx["csrf_token"][:6] + "…") if ctx["csrf_token"] else "-"
        flash_err = ctx["flash_error"] or "-"
        flash_ok = ctx["flash_success"] or "-"
        user_name = ctx["user_name"] or "anonymous"

        return HTMLResponse(
            f"""
            <html>
            <head><title>{settings.APP_NAME}</title></head>
            <body style="font-family: system-ui, sans-serif;">
                <h2>{settings.APP_NAME}</h2>
                <p>Session user: {user_name}</p>
                <p>Flash (error): {flash_err}</p>
                <p>Flash (success): {flash_ok}</p>
                <p>CSRF: {csrf_preview}</p>
                <hr />
                <form method="post" action="/login">
                    <input type="email" name="email" placeholder="email" required />
                    <input type="password" name="password" placeholder="password" required />
                    <button type="submit">Login</button>
                </form>
                <p>Open register modal: <a href="/?show=register">/?show=register</a></p>
            </body>
            </html>
            """,
            status_code=200,
        )

    # Login/Logout
    @app.get("/login")
    async def login_view():
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    @app.post("/login")
    async def login_handler(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: SASession = Depends(get_db),
    ):
        user = await auth_routes.login_post(
            request=request, email=email, password=password, db=db
        )

        if not user:
            if "session" in request.scope:
                request.session["flash_error"] = "Invalid email or password."
            return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

        if "session" in request.scope:
            request.session["user_id"] = user.id
            request.session["user_email"] = user.email
            request.session["user_name"] = user.full_name
            request.session["flash_success"] = "Welcome back!"

        return RedirectResponse("/", status_code=HTTP_302_FOUND)

    @app.post("/logout")
    async def logout(request: Request):
        if "session" in request.scope:
            request.session.clear()
            request.session["_csrf"] = secrets.token_urlsafe(32)
            request.session["flash_success"] = "Signed out."
        return RedirectResponse("/?show=login", status_code=HTTP_302_FOUND)

    # Startup
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
