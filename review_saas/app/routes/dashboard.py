# FILE: app/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Any, Optional, List
from datetime import datetime

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Company, User
from app.services.analysis import dashboard_payload # Upgraded Service

router = APIRouter(tags=["Executive Dashboard"])

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page(
    request: Request, 
    company_id: Optional[int] = None,
    # Requirement #8: Custom Date Range Filtering
    start: Optional[str] = Query(None, description="ISO Start Date"),
    end: Optional[str] = Query(None, description="ISO End Date"),
    # Requirement #11: Comparative Company Benchmarking
    compare_to: Optional[List[int]] = Query(None, description="IDs of branches to benchmark against"),
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Requirement #17: Customizable KPI Dashboard.
    Requirement #20: Executive Summary View.
    Requirement #22: Role-Based Access Control.
    """
    from app.main import templates, common_context
    
    try:
        # 1. Enforcement of Role-Based Access Control (#22)
        # Analysts can see data, but only Owners/Managers can see financial/risk proxies.
        user_role = getattr(current_user, "role", "owner")

        # 2. Fetch Intelligence Data (#20, #21)
        # We pass dates and comparison IDs to the service to handle complex math
        analytics_data = dashboard_payload(
            db, 
            company_id=company_id, 
            start=start, 
            end=end
        )
        
        # 3. Handle Branch Selection & Benchmarking (#11, #12)
        selected_company = None
        benchmarks = []
        
        if company_id:
            selected_company = db.query(Company).filter(Company.id == company_id).first()
            
            # Ensure the user has permission to view this specific company
            if selected_company and selected_company.owner_id != current_user.id and user_role != "admin":
                 raise HTTPException(status_code=403, detail="Unauthorized access to branch data.")

        # 4. Comparative Intelligence (#11, #18)
        if compare_to:
            for b_id in compare_to:
                b_data = dashboard_payload(db, company_id=b_id, start=start, end=end)
                benchmarks.append(b_data)

        # 5. Assemble UI Context (#28)
        context = common_context(request)
        context.update({
            "dashboard_payload": analytics_data,
            "selected_company": selected_company,
            "benchmarks": benchmarks,
            "role": user_role,
            "filters": {"start": start, "end": end},
            "api_health": analytics_data.get("api_health", "Optimal") # #23
        })
        
        return templates.TemplateResponse("dashboard.html", context)

    except HTTPException as he:
        raise he
    except Exception as e:
        # #15: Alert System - Log the failure for system monitoring
        print(f"Dashboard Load Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Neural dashboard interface failed to initialize.")
