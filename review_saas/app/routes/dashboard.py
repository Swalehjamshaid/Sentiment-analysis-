# filename: app/routes/dashboard.py (DIAGNOSTIC VERSION)

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.core.db import get_session
from app.core import models

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

logger = logging.getLogger("app.diagnostics")

@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int,
    start: str,
    end: str,
    db: AsyncSession = Depends(get_session),
):
    # DIAGNOSTIC 1: Confirm the request reached the backend
    print(f"\n🔍 DIAGNOSIS START: Fetching for Company ID: {company_id}")
    print(f"📅 Range requested: {start} to {end}")

    try:
        # Step 1: Check if the company even exists in the DB
        company_query = select(models.Company).where(models.Company.id == company_id)
        company_check = await db.execute(company_query)
        company_exists = company_check.scalar_one_or_none()
        
        if not company_exists:
            print(f"❌ ERROR: Company ID {company_id} NOT FOUND in 'companies' table.")
        else:
            print(f"✅ SUCCESS: Found Company '{company_exists.name}' in database.")

        # Step 2: Run the review query
        query = select(models.Review).where(models.Review.company_id == company_id)
        result = await db.execute(query)
        reviews = result.scalars().all()

        # DIAGNOSTIC 2: Report what was found in the 'reviews' table
        print(f"📊 DATABASE RESULT: Found {len(reviews)} review records for this ID.")

        if not reviews:
            # Check if there are ANY reviews at all in the database
            total_check = await db.execute(select(models.Review))
            all_reviews_count = len(total_check.scalars().all())
            print(f"⚠️  WARNING: No reviews for ID {company_id}, but there are {all_reviews_count} total reviews in the DB.")
            
            return JSONResponse(content={
                "metadata": {"total_reviews": 0, "diag": "Check logs for ID mismatch"},
                "kpis": {},
                "visualizations": {}
            })

        # ... (rest of your logic for KPIs would go here)
        return {"status": "success", "count": len(reviews)}

    except Exception as e:
        print(f"💥 CRITICAL DATABASE ERROR: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})
