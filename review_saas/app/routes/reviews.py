# filename: app/routes/reviews.py

# ... (other imports)
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

# ... (get_company_reviews endpoint)

@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 1. Trigger Full Ingestion
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 2. Fetch details for response (Must be awaited now!)
        details = await fetch_place_details(place_id)
        
        return {
            "success": True, 
            "message": "Full history sync complete",
            "company_name": details.get("name")
        }
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
