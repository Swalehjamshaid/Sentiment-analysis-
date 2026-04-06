# filename: app/main.py

import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

# -------------------------------
# CORE IMPORTS
# -------------------------------
from app.core.config import settings
from app.core.db import init_models, get_db
from app.routes import auth, companies, dashboard, reviews, exports, google_check

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# -------------------------------
# PASSWORD HASHING
# -------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------------------
# LIFESPAN (SAFE STARTUP)
# -------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Review Intel AI...")

    try:
        await asyncio.sleep(1)

        # Initialize DB safely
        await init_models()

        logger.info("✅ Database Initialized")

    except Exception as e:
        logger.error(f"❌ Startup Failed: {e}")

    yield

    logger.info("🛑 Shutdown complete")


# -------------------------------
# APP INIT
# -------------------------------
app = FastAPI(
    title="Review Intel AI",
    lifespan=lifespan
)

# -------------------------------
# MIDDLEWARE
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY
)

# -------------------------------
# STATIC & TEMPLATES
# -------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "templates")
)

# -------------------------------
# ROUTES (UI)
# -------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    from app.core.models import User  # local import to avoid circular issue

    result = await db.execute(
        select(User).where(User.email == email.strip().lower())
    )
    user = result.scalars().first()

    if user and pwd_context.verify(password, user.hashed_password):
        request.session["user"] = {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
        return RedirectResponse("/dashboard", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid email or password"}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": request.session.get("user")
        }
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# -------------------------------
# API ROUTES
# -------------------------------
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])


# -------------------------------
# ENTRYPOINT (LOCAL ONLY)
# -------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=True
    )
