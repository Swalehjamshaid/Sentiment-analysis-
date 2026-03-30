import os
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import google.generativeai as genai

# Core Imports
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/chatbot", tags=["chatbot"])
logger = logging.getLogger(__name__)

# --- HARDCODED AI CONFIGURATION ---
API_KEY = "AIzaSyB-J-JRHFepz-oKtre8zM3iXucAdM7BBn4"

model = None
try:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-pro")
    logger.info("Gemini AI initialized successfully")
except Exception as e:
    logger.error(f"Gemini Config Error: {e}")
    model = None


@router.post("/chat")
async def chat_api(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    try:
        # 1. Session Check
        user = request.session.get("user")
        if not user:
            logger.warning("Chatbot accessed without active session")

        # 2. Parse Request
        body = await request.json()
        company_id_raw = body.get("company_id")
        user_message = body.get("message", "").strip()

        if not company_id_raw or company_id_raw == "null":
            return JSONResponse({
                "answer": "AI Expert: Please select a business from the dashboard dropdown first."
            })

        # 3. Validate Company ID
        try:
            company_id = int(company_id_raw)
        except (ValueError, TypeError):
            return JSONResponse({
                "answer": "AI Expert: Invalid Business ID. Please re-select the business."
            })

        # 4. Fetch Company
        comp_stmt = select(Company).where(Company.id == company_id)
        comp_res = await session.execute(comp_stmt)
        company = comp_res.scalar_one_or_none()

        if not company:
            return JSONResponse({
                "answer": f"AI Expert: I cannot find Business ID {company_id} in the PostgreSQL database."
            })

        # 5. Fetch Reviews
        rev_stmt = (
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.date.desc())
            .limit(40)
        )
        rev_res = await session.execute(rev_stmt)
        reviews = rev_res.scalars().all()

        # Railway Logs
        logger.info(f"--- Chatbot Analysis for: {company.name} ---")
        logger.info(f"Reviews found: {len(reviews)}")

        # 6. AI Response
        if model:
            if reviews:
                review_context = "\n".join([
                    f"Rating: {r.rating}* | {r.text or ''}" for r in reviews
                ])

                prompt = f"""
You are a Business Consultant for {company.name}.

Analyze these customer reviews from our database:
{review_context}

User Question: {user_message}

Instruction: Provide a professional, concise answer based ONLY on the review data.
"""
            else:
                prompt = f"""
The user is asking about {company.name}, but there are no reviews in the database.
Tell them to click 'Sync Live Data'.

User asked: {user_message}
"""

            try:
                response = model.generate_content(prompt)

                # Safe extraction
                answer_text = None
                if response:
                    if hasattr(response, "text") and response.text:
                        answer_text = response.text
                    elif hasattr(response, "candidates") and response.candidates:
                        try:
                            answer_text = response.candidates[0].content.parts[0].text
                        except Exception:
                            answer_text = None

                if answer_text:
                    return JSONResponse({"answer": answer_text.strip()})
                else:
                    return JSONResponse({
                        "answer": "AI Expert: I processed the data but the AI did not return text. Please try again."
                    })

            except Exception as ai_error:
                logger.error(f"Gemini Runtime Error: {ai_error}")
                return JSONResponse({
                    "answer": "AI Expert: AI processing failed. Please try again."
                })

        return JSONResponse({
            "answer": "AI Expert: Gemini AI Model is not initialized."
        })

    except Exception as e:
        logger.error(f"Chatbot Critical Error: {e}", exc_info=True)
        return JSONResponse({
            "answer": f"AI Expert Error: {str(e)}"
        }, status_code=500)
