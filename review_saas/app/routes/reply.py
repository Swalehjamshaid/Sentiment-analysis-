from fastapi import APIRouter

    router = APIRouter(prefix="/reply", tags=["reply"])

    @router.post("/suggest")
    def suggest(text: str, sentiment: str | None = None):
        s = (sentiment or "").lower()
        if s == "negative":
            msg = "We’re sorry about your experience. Please contact support@example.com so we can help."
        elif s == "positive":
            msg = "Thank you for your kind words! We truly appreciate your feedback."
        else:
            msg = "Thanks for the feedback. We value your input and will keep improving."
        return {"suggested": msg[:500]}