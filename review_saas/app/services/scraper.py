import os
import csv
import asyncio
import logging
from app.services.scraper import ReviewScraper

# =========================
# LOGGING CONFIG
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ReviewsIngestor")

# =========================
# MULTI-BUSINESS LIST
# Replace with your real place names and IDs
# =========================
BUSINESSES = [
    {"name": "Salt'n Pepper Village Lahore", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"},
    {"name": "Food Street Karachi", "place_id": "ChIJSx6rE9vFzDkR_F5PQhLwG3Y"},
    # Add more businesses here
]

# =========================
# CSV OUTPUT SETTINGS
# =========================
OUTPUT_CSV = "reviews_output.csv"
CSV_FIELDS = [
    "place_name", "review_id", "author_name", "rating", "text", "time"
]

# =========================
# ASYNC INGEST FUNCTION
# =========================
async def ingest_place(scraper: ReviewScraper, business: dict):
    """
    Fetch and return reviews for a single business
    """
    place_name = business["name"]
    place_id = business["place_id"]
    logger.info(f"Fetching reviews for: {place_name}")

    # Fetch reviews
    reviews = scraper.fetch_reviews(place_id)
    if not reviews:
        logger.warning(f"No reviews found for {place_name}")
        return []

    processed_reviews = []
    for item in reviews:
        if not isinstance(item, dict):
            continue
        processed_reviews.append({
            "place_name": place_name,
            "review_id": item.get("review_id", ""),
            "author_name": item.get("user_name", ""),
            "rating": item.get("rating", ""),
            "text": item.get("text", ""),
            "time": item.get("time", "")
        })
    return processed_reviews

# =========================
# MAIN ASYNC FUNCTION
# =========================
async def main():
    scraper = ReviewScraper()
    all_reviews = []

    # Run all businesses concurrently
    tasks = [ingest_place(scraper, b) for b in BUSINESSES]
    results = await asyncio.gather(*tasks)

    # Flatten results
    for res in results:
        if res:
            all_reviews.extend(res)

    # Save to CSV
    if all_reviews:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(all_reviews)
        logger.info(f"Saved {len(all_reviews)} reviews to {OUTPUT_CSV}")
    else:
        logger.warning("No reviews fetched for any business.")

# =========================
# RUN SCRIPT
# =========================
if __name__ == "__main__":
    asyncio.run(main())
