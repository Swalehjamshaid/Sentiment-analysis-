from fastapi import APIRouter

    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/kpis")
    def kpis():
        return {"totals": {"reviews": 0, "avg_rating": 0.0}, "mix": {"positive": 0, "neutral": 0, "negative": 0}}