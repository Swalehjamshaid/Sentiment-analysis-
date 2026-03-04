# filename: app/services/google_reviews.py

async def ingest_company_reviews(company_id: int, place_id: str):
    """
    Fetch reviews from Google Business API or Places API, store in database.
    """
    logger.info(f"Starting review ingestion for company_id={company_id}")

    try:
        # Fetch reviews
        reviews = await _fetch_reviews_from_business_api(place_id)
        if not reviews:
            logger.info("Falling back to Google Places API.")
            reviews = _fetch_reviews_from_places_api(place_id)

        if not reviews:
            logger.info("No reviews found from Google.")
            return

        async with get_session() as session:
            for r in reviews:
                # Extract fields for both API formats
                author = r.get("reviewer", {}).get("displayName") if "reviewer" in r else r.get("author_name")
                rating = r.get("starRating") if "starRating" in r else r.get("rating")
                text = r.get("comment") if "comment" in r else r.get("text")
                profile_photo = r.get("reviewer", {}).get("profilePhotoUrl") if "reviewer" in r else r.get("profile_photo_url")

                review_date = None
                if "createTime" in r:
                    review_date = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                elif "time" in r:
                    review_date = datetime.utcfromtimestamp(r["time"])

                # Skip duplicates
                existing = await session.execute(
                    select(Review).where(
                        Review.company_id == company_id,
                        Review.author_name == author,
                        Review.text == text
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Create review object
                new_review = Review(
                    company_id=company_id,
                    author_name=author,
                    rating=int(rating) if rating else None,
                    text=text,
                    review_date=review_date,
                    source="google",
                    profile_photo=profile_photo,
                )
                session.add(new_review)

            # Push all changes to DB
            await session.flush()
            await session.commit()

        logger.info("Google review ingestion completed successfully.")

    except Exception as e:
        logger.error(f"Failed to ingest Google reviews: {e}")
