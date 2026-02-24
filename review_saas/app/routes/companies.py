# File: app/routes/companies.py

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    try:
        company_count = db.query(Company).count()
        review_count = db.query(Review).count()

        # 1. YOU MUST DEFINE THIS VARIABLE
        # In a real app, you'd fetch these from the DB. 
        # Here is a professional default structure:
        dashboard_payload = {
            "metrics": {
                "total": review_count,
                "avg_rating": 4.5, # Replace with db calculation
                "risk_score": 15,
                "risk_level": "Low"
            },
            "date_range": {
                "start": "2026-01-01",
                "end": "2026-02-24"
            },
            "trend": {"signal": "stable", "delta": 0, "labels": [], "data": []},
            "sentiment": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "heatmap": {"labels": [], "data": []},
            "reviews": {"total": review_count, "data": []}
        }

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "dashboard_payload": dashboard_payload, # 2. PASS IT HERE
                "companies": db.query(Company).all()
            }
        )
    except Exception as e:
        logger.error(f"Critical error rendering dashboard: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error loading the dashboard interface.")
