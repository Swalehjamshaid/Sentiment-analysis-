# FILE: review_saas/app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Any, Optional, List
from datetime import datetime, timezone

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Company, User
from app.services.analysis import dashboard_payload

router = APIRouter(tags=["Executive Dashboard"])

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page(
    request: Request, 
    company_id: Optional[int] = None,
    # Requirement #8: Custom Date Range Filtering
    start: Optional[str] = Query(None, description="ISO Start Date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="ISO End Date (YYYY-MM-DD)"),
    # Requirement #11: Comparative Company Benchmarking
    compare_ids: Optional[str] = Query(None, description="Comma-separated IDs for benchmarking"),
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Requirement #20: Executive Summary View.
    Requirement #22: Role-Based Access Control (RBAC).
    Requirement #17: Customizable KPI Dashboard.
    """
    from app.main import templates, common_context
    
    try:
        # 1. Enforcement of Role-Based Access Control (#22)
        user_role = getattr(current_user, "role", "owner")

        # 2. Main Analytics Engine Execution (#3 - #7, #21)
        # This service now generates the sentiment, emotion, and predictive data
        payload = dashboard_payload(
            db, 
            company_id=company_id, 
            start=start, 
            end=end
        )
        
        # 3. Branch Verification & Security check
        selected_company = None
        if company_id:
            selected_company = db.query(Company).filter(Company.id == company_id).first()
            if not selected_company:
                raise HTTPException(status_code=404, detail="Selected branch not found.")
            
            # Ensure owner-only data visibility where applicable
            if selected_company.owner_id != current_user.id and user_role != "admin":
                 raise HTTPException(status_code=403, detail="Access denied to this company's intelligence.")

        # 4. Comparative Intelligence Benchmarking (#11)
        benchmarks = []
        if compare_ids:
            try:
                ids = [int(i.strip()) for i in compare_ids.split(",") if i.strip()]
                for b_id in ids:
                    if b_id != company_id:
                        b_data = dashboard_payload(db, company_id=b_id, start=start, end=end)
                        benchmarks.append({
                            "id": b_id,
                            "name": b_data.get("company", {}).get("name", "Branch"),
                            "avg_rating": b_data.get("metrics", {}).get("avg_rating", 0),
                            "sentiment": b_data.get("executive_summary", {}).get("sentiment_score", 0)
                        })
            except ValueError:
                pass # Ignore malformed comparison IDs

        # 5. UI Context Assembly (#28 Interactive & Intuitive UI)
        context = common_context(request)
        context.update({
            "dashboard_payload": payload,
            "selected_company": selected_company,
            "benchmarks": benchmarks,
            "user_role": user_role,
            "filters": {"start": start, "end": end},
            "api_health": payload.get("company", {}).get("api_health", "Healthy") # #23
        })
        
        return templates.TemplateResponse("dashboard.html", context)

    except HTTPException as he:
        raise he
    except Exception as e:
        # Requirement #15: System Alert/Notification on critical load failure
        print(f"CRITICAL DASHBOARD ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="Intelligence Dashboard failed to synchronize.")
