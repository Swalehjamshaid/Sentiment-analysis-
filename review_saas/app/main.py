import os
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates
    from fastapi.staticfiles import StaticFiles
    from apscheduler.schedulers.background import BackgroundScheduler
    from .routes import auth, companies, dashboard, reviews, reply, reports, admin
    from .db import engine
    from .models import Base

    app = FastAPI(title="Review SaaS")
    templates = Jinja2Templates(directory="app/templates")

    # Mount uploads if folder exists
    if os.path.isdir("app_uploads"):
        app.mount("/uploads", StaticFiles(directory="app_uploads"), name="uploads")

    @app.on_event("startup")
    def _init_db():
        Base.metadata.create_all(bind=engine)
        if os.getenv("ENABLE_SCHEDULER") == "1":
            scheduler = BackgroundScheduler()
            scheduler.start()

    # Basic UI routes
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse("home.html", {"request": request})

    @app.get("/register", response_class=HTMLResponse)
    def register_page(request: Request):
        return templates.TemplateResponse("register.html", {"request": request})

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request})

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_page(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request})

    @app.get("/report", response_class=HTMLResponse)
    def report_page(request: Request):
        return templates.TemplateResponse("report.html", {"request": request})

    # APIs
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