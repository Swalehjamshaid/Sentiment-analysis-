import logging
import re
from collections import Counter
from typing import List, Set
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review

logger = logging.getLogger(__name__)

# List of common words to ignore during keyword extraction to ensure quality results
STOP_WORDS: Set[str] = {
    'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'in', 'on', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'of', 'off',
    'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where',
    'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 
    'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 
    'can', 'will', 'just', 'should', 'now', 'hotel', 'stay', 'place', 'rooms', 'service',
    'really', 'they', 'them', 'their', 'what', 'which', 'who', 'whom', 'this', 'that'
}

class KeywordService:
    @staticmethod
    def extract_keywords(text: str, top_n: int = 5) -> List[str]:
        """
        Cleans raw review text and extracts the most frequent meaningful keywords.
        """
        if not text or len(text.strip()) < 10:
            return []

        # Remove special characters and split into lowercase words
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        
        # Filter out stop words and common noise
        filtered_words = [
            word for word in words 
            if word not in STOP_WORDS
        ]

        # Count frequencies and return the top N keywords
        counts = Counter(filtered_words)
        return [word for word, count in counts.most_common(top_n)]

    async def process_company_reviews_keywords(self, company_id: int):
        """
        Batch processes all reviews for a specific company that currently lack keywords.
        This aligns with the Outscraper ingestion by processing newly added reviews.
        """
        async with get_session() as session:
            try:
                # Select reviews for this company that haven't been processed yet
                stmt = select(Review).where(
                    Review.company_id == company_id,
                    Review.text.isnot(None)
                )
                result = await session.execute(stmt)
                reviews = result.scalars().all()

                if not reviews:
                    logger.info(f"No reviews found to process keywords for company {company_id}")
                    return

                processed_count = 0
                for review in reviews:
                    # Only process if keywords are currently empty or null
                    if not review.keywords:
                        extracted = self.extract_keywords(review.text)
                        review.keywords = extracted
                        processed_count += 1
                
                await session.commit()
                logger.info(f"Successfully updated keywords for {processed_count} reviews for company {company_id}")
                
            except Exception as e:
                logger.error(f"Error in KeywordService for company {company_id}: {str(e)}")
                await session.rollback()

# Initialize a singleton instance for use across the application
keyword_service = KeywordService()
