from fastapi import FastAPI, Request, Response, Depends
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates
    from fastapi.staticfiles import StaticFiles
    from .routes import auth, companies, dashboard, reviews, reply, reports, admin
    from .db import engine
    from .models import Base

    app = FastAPI(title="Review SaaS")
    templates = Jinja2Templates(directory="app/templates")

    # Create tables on startup
    @app.on_event("startup")
    def _init_db():
        Base.metadata.create_all(bind=engine)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse("home.html", {"request": request})

    app.include_router(auth.router)
    app.include_router(companies.router)
    app.include_router(dashboard.router)
    app.include_router(reviews.router)
    app.include_router(reply.router)
    app.include_router(reports.router)
    app.include_router(admin.router)

    @app.get("/health")
    def health():
        return {"ok": True}