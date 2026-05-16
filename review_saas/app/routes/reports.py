# ==========================================================
# FILE: app/routes/reports.py
# ==========================================================

from __future__ import annotations

import os
import logging

from fastapi import (
    APIRouter,
    Request,
    Depends,
    HTTPException,
    status,
)

from fastapi.responses import (
    FileResponse,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.report_service import ReportService

logger = logging.getLogger("app.reports")

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/api/reports",
    tags=["Reports"]
)

# ==========================================================
# REPORT SERVICE
# ==========================================================

report_service = ReportService()

# ==========================================================
# AUTH CHECK
# ==========================================================

def require_user(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )

    return user_id

# ==========================================================
# DOWNLOAD EXECUTIVE REPORT
# ==========================================================

@router.get("/{company_id}/download")

async def generate_report(

    company_id: int,

    request: Request,

    session: AsyncSession = Depends(get_db),

):

    require_user(request)

    try:

        # ==================================================
        # GENERATE PDF
        # ==================================================

        pdf_path = await report_service.generate_executive_report(

            session=session,

            company_id=company_id,
        )

        # ==================================================
        # CHECK PDF EXISTS
        # ==================================================

        if not os.path.exists(pdf_path):

            raise HTTPException(

                status_code=404,

                detail="PDF report not found"
            )

        logger.info(
            "✅ Executive report generated for company_id=%s",
            company_id
        )

        # ==================================================
        # RETURN PDF
        # ==================================================

        return FileResponse(

            path=pdf_path,

            media_type="application/pdf",

            filename=os.path.basename(pdf_path)
        )

    except HTTPException:

        raise

    except Exception as e:

        logger.exception(
            "❌ Failed to generate executive report"
        )

        raise HTTPException(

            status_code=500,

            detail=f"Failed to generate report: {str(e)}"
        )
