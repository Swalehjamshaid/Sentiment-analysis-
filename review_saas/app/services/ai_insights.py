
import os
from typing import Optional

# Modern Google GenAI SDK
try:
    from google import genai  # type: ignore
except Exception:
    genai = None

MODEL_NAME = "gemini-1.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = None
if GEMINI_API_KEY and genai:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        client = None

async def generate_ai_reply(review_text: str, rating: int, company_name: str) -> str:
    if not client:
        return "Thank you for your feedback. We value your input."
    prompt = (
        f"Write a professional response for {company_name} "
        f"to this {rating}-star review: '{review_text}'. Keep it under 60 words."
    )
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        if response and getattr(response, 'text', None):
            return response.text.strip()
    except Exception:
        pass
    return "Thank you for your feedback. We value your input."

def suggest_reply(review_text: str, rating: int, company_name: str) -> str:
    import asyncio
    try:
        return asyncio.run(generate_ai_reply(review_text, rating, company_name))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(generate_ai_reply(review_text, rating, company_name))
