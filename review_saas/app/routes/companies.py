# filename: review_saas/app/routes/companies.py

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_session, AsyncSessionLocal
from app.core.models import Company
from app.services.google_reviews import run_batch_review_ingestion

logger = logging.getLogger("app.companies")

router = APIRouter(prefix="/api/companies", tags=["companies"])


# ----------------------------------------
# BACKGROUND INGESTION WRAPPER
# ----------------------------------------
async def background_review_ingestion(client, company):
    """
    Creates a fresh DB session for the background task.
    Prevents Railway session closed errors.
    """
    async with AsyncSessionLocal() as session:
        try:
            await run_batch_review_ingestion(
                client,
                [company],
                session=session,
            )
        except Exception as e:
            logger.error("Background ingestion failed for company %s: %s", company.id, e)


# ----------------------------------------
# LIST COMPANIES
# ----------------------------------------
@router.get("/")
async def list_companies(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Company))
    companies = result.scalars().all()
    return companies


# ----------------------------------------
# CREATE COMPANY
# ----------------------------------------
@router.post("/")
async def create_company(
    data: dict,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    try:
        company = Company(
            name=data.get("name"),
            address=data.get("address"),
            google_place_id=data.get("google_place_id"),
            website=data.get("website"),
        )

        session.add(company)
        await session.commit()
        await session.refresh(company)

        logger.info("Company created with ID %s", company.id)

    except Exception as e:
        await session.rollback()
        logger.error("Company creation failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create company")

    # ----------------------------------------
    # TRIGGER REVIEW INGESTION
    # ----------------------------------------
    try:
        from app.services.outscraper_client import OutscraperClient

        client = OutscraperClient()

        background.add_task(
            background_review_ingestion,
            client,
            company,
        )

        logger.info("Review ingestion scheduled for company %s", company.id)

    except Exception as e:
        logger.warning("Failed to schedule review ingestion: %s", e)

    return {
        "status": "success",
        "company_id": company.id,
        "message": "Company created successfully",
    }


# ----------------------------------------
# GET SINGLE COMPANY
# ----------------------------------------
@router.get("/{company_id}")
async def get_company(company_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return company


# ----------------------------------------
# DELETE COMPANY
# ----------------------------------------
@router.delete("/{company_id}")
async def delete_company(company_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    await session.delete(company)
    await session.commit()

    return {"message": "Company deleted successfully"}
