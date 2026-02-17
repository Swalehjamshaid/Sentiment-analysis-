# Placeholder for scheduled tasks (e.g., review fetching). In production,
    # wire APScheduler or a cron job to call services.google_places.fetch_for_company.
    from .core.settings import settings

    async def schedule_fetch_reviews():
        return {"status": "scheduled"}