from fastapi import APIRouter
    from ..services.reply import suggest

    router = APIRouter(prefix="/reply", tags=["reply"])

    @router.post("/suggest")
    def suggest_reply(text: str):
        return {"suggested": suggest(text)}