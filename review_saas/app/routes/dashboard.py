# filename: app/routes/dashboard.py

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_session
from app.models import User, Review, Company  # adjust imports according to your project
from app.templates import templates  # make sure templates are correctly imported
import logging
from sqlalchemy.future import select

router = APIRouter()

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Dependency to get current user (adjust your auth logic)
async def get_current_user(request: Request) -> User:
    try:
        # Example: retrieve user info from session/cookie
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        async with get_async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            return user
    except Exception as e:
        logger.exception("Error fetching current user")
        return None


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_async_session)):
    try:
        # Get current user
        current_user = await get_current_user(request)
        if not current_user:
            logger.warning("No current user found for dashboard")
            return HTMLResponse(content="User not logged in.", status_code=401)

        # Fetch companies
        result = await session.execute(select(Company))
        companies = result.scalars().all() or []

        # Fetch reviews safely
        result = await session.execute(select(Review))
        reviews = result.scalars().all() or []

        # Build chart data (example, adapt to your actual logic)
        chart_data = {
            "total_reviews": len(reviews),
            "reviews_by_company": {c.id: 0 for c in companies}
        }
        for r in reviews:
            if r.company_id in chart_data["reviews_by_company"]:
                chart_data["reviews_by_company"][r.company_id] += 1

        context = {
            "request": request,
            "user": current_user,
            "companies": companies,
            "reviews": reviews,
            "charts": chart_data
        }

        return templates.TemplateResponse("dashboard.html", context)

    except Exception as e:
        logger.exception("Dashboard route error:")
        # Return friendly message to the frontend
        return HTMLResponse(content=f"Error loading dashboard: {str(e)}", status_code=500)
