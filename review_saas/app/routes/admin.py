from fastapi import APIRouter

    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/stats")
    def stats():
        return {"ok": True, "message": "Admin stats placeholder"}