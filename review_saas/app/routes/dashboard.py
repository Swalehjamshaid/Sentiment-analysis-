# Updated Debug Endpoint for app/routes/dashboard.py

@router.get("/api/debug/company-check")
async def debug_company_check():
    """
    DEBUG: Returns a clear mapping of Company Name -> ID -> Review Count
    """
    async with get_session() as session:
        # Join Company and Review tables to get a summary by name
        stmt = (
            select(
                Company.id,
                Company.name,
                func.count(Review.id).label("total_reviews")
            )
            .outerjoin(Review, Company.id == Review.company_id)
            .group_by(Company.id, Company.name)
        )
        
        result = await session.execute(stmt)
        data = result.all()
        
        return {
            "summary": [
                {
                    "company_name": r.name,
                    "id_to_use_in_dashboard": r.id,
                    "reviews_found": r.total_reviews
                } 
                for r in data
            ]
        }
