import asyncio
from textblob import TextBlob
from sqlalchemy import select, update
from app.core.db import get_session
from app.core.models import Review, Company

async def fix_dashboard_data():
    async with get_session() as session:
        print("--- Step 1: Aligning Company IDs ---")
        # Fix for McDonald's: Moving from ID 7 to ID 1
        await session.execute(
            update(Review).where(Review.company_id == 7).values(company_id=1)
        )
        
        # Fix for Fabric London: Moving from ID 8 to ID 2
        await session.execute(
            update(Review).where(Review.company_id == 8).values(company_id=2)
        )
        print("✓ Reviews reassigned to correct Dashboard IDs (1 and 2).")

        print("\n--- Step 2: Processing Missing Sentiment ---")
        # Fetch reviews where sentiment_score is NULL (as seen in your Postgres screenshot)
        stmt = select(Review).where(Review.sentiment_score == None)
        result = await session.execute(stmt)
        reviews_to_process = result.scalars().all()

        if not reviews_to_process:
            print("No NULL sentiment records found.")
        else:
            for review in reviews_to_process:
                if not review.text:
                    continue
                
                # Calculate Polarity using TextBlob
                analysis = TextBlob(review.text)
                score = analysis.sentiment.polarity
                
                # Assign Label based on score
                if score > 0.1:
                    label = "positive"
                elif score < -0.1:
                    label = "negative"
                else:
                    label = "neutral"

                review.sentiment_score = score
                review.sentiment_label = label
                print(f"Processed Review {review.id}: {label} ({score:.2f})")

        # Save changes to Railway Postgres
        await session.commit()
        print("\n✓ Data Repair Complete. Refresh your dashboard now.")

if __name__ == "__main__":
    asyncio.run(fix_dashboard_data())
