# filename: app/main.py
import os
import asyncio
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

# Safe Imports
from app.core.config import settings
from app.routes import auth, companies, dashboard, reviews, exports, google_check

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Fresh Start Sequence Initiated...")
    try:
        # Delayed DB import to avoid circular imports
        from app.core.db import init_models
        await asyncio.sleep(1)
        await init_models()  # Rebuild tables if schema changed
    except Exception as e:
        print(f"❌ Startup Failed: {e}")
    yield

app = FastAPI(title="Review Intel AI", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static & Templates
APP_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

@app.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(lambda: __import__('app.core.db', fromlist=['get_db']).get_db())
):
    from app.core.models import User  # Delayed import
    db_gen = await db()
    async with db_gen as session:
        res = await session.execute(select(User).where(User.email == email.strip().lower()))
        user = res.scalars().first()
        if user and pwd_context.verify(password, user.hashed_password):
            request.session["user"] = {"id": user.id, "email": user.email, "name": user.name}
            return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid login"})

# Include Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(exports.router, prefix="/api", tags=["exports"])
app.include_router(google_check.router, prefix="/api", tags=["google_check"])
