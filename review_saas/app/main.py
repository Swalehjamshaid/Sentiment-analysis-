# app/main.py

# ... (Keep all existing imports at the top) ...

# ─────────────────────────────────────────────────────────────
# REAL DATA Local Routes: This fixes the 500 Error
# ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if user:
        # If logged in, send them directly to their real dashboard
        user_db = db.query(User).filter(User.id == user.id).first()
        if user_db and user_db.companies:
            return RedirectResponse(f"/dashboard/{user_db.companies[0].id}")
    
    # Otherwise, show a clean, empty dashboard state
    context = common_context(request)
    context.update({
        "current_user": user, "companies": [], "selected_company": None,
        "kpi": {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "growth": "0%"},
        "charts": {"labels": [], "sentiment": [], "rating": []},
        "reviews": [], "summary": "Welcome to ReviewIQ. Please login to begin."
    })
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/dashboard/{company_id}", response_class=HTMLResponse)
async def dashboard_view(request: Request, company_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    # Fetch Real Company Data from Postgres
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return RedirectResponse("/")

    # Fetch Real Metrics using your existing services
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)
    
    real_kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, start_date, end_date)
    real_charts = metrics_svc.build_dashboard_charts(db, company_id, start_date, end_date)
    
    # Fetch Real Review List
    real_reviews = db.query(Review).filter(Review.company_id == company_id).order_by(Review.review_date.desc()).limit(10).all()

    context = common_context(request)
    context.update({
        "current_user": user,
        "selected_company": company,
        "active_company": company,
        "companies": db.query(Company).filter(Company.owner_id == user.id).all(),
        "kpi": real_kpi,
        "charts": real_charts,
        "reviews": real_reviews,
        "summary": "Displaying real-time analysis for " + company.name,
        "params": {"from": start_date.date().isoformat(), "to": end_date.date().isoformat(), "range": "30d"}
    })
    return templates.TemplateResponse("dashboard.html", context)
