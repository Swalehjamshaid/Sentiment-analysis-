# filename: app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import routers (you need to create these modules later)
from app.routers import (
    users,          # user registration, login, profile
    companies,      # company CRUD
    reviews,        # fetch/store reviews
    sentiment,      # sentiment analysis
    ai_replies,     # suggested replies
    dashboard,      # dashboard & visualization
    reports         # PDF/report generation
)

from app.core.auth import configure_auth  # JWT, password hashing, login attempts, 2FA, etc.

def create_app() -> FastAPI:
    app = FastAPI(
        title="Review SaaS Platform",
        description="Multi-company review monitoring & AI-assisted response system",
        version="1.0.0",
    )

    # CORS (adjust origins for production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files for profile pictures, logos, etc.
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Configure authentication (JWT, password hashing, login attempt tracking)
    configure_auth(app)

    # Include routers
    app.include_router(users.router, prefix="/users", tags=["Users"])
    app.include_router(companies.router, prefix="/companies", tags=["Companies"])
    app.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
    app.include_router(sentiment.router, prefix="/sentiment", tags=["Sentiment"])
    app.include_router(ai_replies.router, prefix="/replies", tags=["AI Replies"])
    app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
    app.include_router(reports.router, prefix="/reports", tags=["Reports"])

    return app

# Create the app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    # Dev server
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)
