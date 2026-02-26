# filename: review_saas/app/main.py
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.status import HTTP_302_FOUND

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

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in production
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

    # NOTE:
    # We previously tried to render templates if present, but your logs show
    # templates aren't ready ('NoneType' callable warnings). To keep logs clean
    # and UX simple, we will *not* attempt template rendering until you add them.

    # Include routers (Register endpoints live here)
    app.include_router(auth_routes.router)

    # Home (fallback HTML)
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """
        Minimal HTML UI that supports:
          - /?show=login
          - /?show=register
        It also ensures a CSRF token exists in session, so /register POST works.
        """
        show = request.query_params.get("show")

        # ✅ Ensure CSRF exists now that we're inside a route (SessionMiddleware attached)
        csrf_token: Optional[str] = None
        if "session" in request.scope:
            if request.session.get("_csrf") is None:
                request.session["_csrf"] = secrets.token_urlsafe(32)
            csrf_token = request.session.get("_csrf")

        # Flash messages
        flash_error = request.session.pop("flash_error", None) if "session" in request.scope else None
        flash_success = request.session.pop("flash_success", None) if "session" in request.scope else None

        user_name = request.session.get("user_name") if "session" in request.scope else None

        # Fallback UI
        csrf_preview = (csrf_token[:6] + "…") if csrf_token else "-"

        # ---- Login form (default) ----
        login_section = f"""
            <form action="/login" method="post">
                <input type="email" name="email" placeholder="email" required />
                <input type="password" name="password" placeholder="password" required />
                <button type="submit">Login</button>
            </form>
            <p>Open register form: <a href="/?show=register">/?show=register</a></p>
        """

        # ---- Register form (when show=register) ----
        register_section = ""
        if show == "register":
            # Render a basic register form that matches your /register POST
            csrf_hidden = csrf_token or ""
            register_section = f"""
            <h3>Register</h3>
            <form action="/register" method="post">
                <input type="text" name="name" placeholder="full name" />
                <input type="email" name="email" placeholder="email" required />
                <input type="password" name="password" placeholder="password" required />
                <input type="hidden" name="csrf_token" value="{csrf_hidden}" />
                <button type="submit">Create Account</button>
            </form>
            <p>Back to login: <a href="/?show=login">/?show=login</a></p>
            """

        html = f"""
        <html>
        <head><title>{settings.APP_NAME}</title></head>
        <body style="font-family: system-ui, sans-serif; max-width: 700px; margin: 24px auto;">
            <h2>{settings.APP_NAME}</h2>

            <p><strong>Session user:</strong> {user_name or "anonymous"}</p>
            <p><strong>Flash (error):</strong> {flash_error or "-"}</p>
            <p><strong>Flash (success):</strong> {flash_success or "-"}</p>
            <p><strong>CSRF:</strong> {csrf_preview}</p>
            <hr />
            {"<h3>Login</h3>" + login_section if show != "register" else register_section}
        </body>
        </html>
        """
        return HTMLResponse(html, status_code=200)

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
            # regenerate CSRF for next session
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
