import httpx
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    """
    A high-speed Google Review scraper using direct request emulation.
    Bypasses the overhead of Selenium for 10x faster execution.
    """
    def __init__(self):
        # Using a mobile User-Agent to trigger Google's lightweight AJAX response
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def get_reviews(self, data_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches reviews directly from Google's internal AJAX endpoint.
        
        :param data_id: The unique Google 'feature_id' (e.g., ChIJzVjKHacFGTkR1B_Hr2EH9iA).
        :param limit: Number of reviews to fetch (Google typically caps individual requests at 199).
        """
        # Google's raw AJAX data endpoint
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # The 'pb' parameter is a Protobuf-style string that defines the request payload
        # !1i0 = start index, !2i{limit} = count, !3e1 = sort by newest
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": f"!1m1!1s{data_id}!2m2!1i0!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
        }

        reviews_list = []
        
        async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
            try:
                response = await client.get(url, params=params)
                
                # Google prefixes their JSON with security characters to prevent hijacking
                if response.text.startswith(")]}'"):
                    clean_text = response.text.replace(")]}'\n", "")
                else:
                    clean_text = response.text

                data = json.loads(clean_text)

                # Drill down into the nested list structure returned by Google
                if not data or len(data) < 3 or data[2] is None:
                    logger.warning(f"No reviews found in response for data_id: {data_id}")
                    return []

                for r in data[2]:
                    try:
                        # Map indices to match your Review model and dashboard requirements
                        review_item = {
                            "review_id": str(r[0]),
                            "rating": int(r[4]),
                            "text": r[3] if r[3] else "",
                            "author_title": r[0][1] if r[0] and len(r[0]) > 1 else "Anonymous User",
                            "author_id": r[6],
                            "author_image": r[0][2] if r[0] and len(r[0]) > 2 else None,
                            # Convert Google's millisecond timestamp to ISO string
                            "review_datetime_utc": datetime.fromtimestamp(r[27]/1000).isoformat() if r[27] else datetime.now().isoformat(),
                            # Check for business owner replies
                            "owner_answer": r[9][1] if r[9] and len(r[9]) > 1 else None,
                            # Extract photo URLs if present
                            "reviews_photos": [p[1][0][6][0] for p in r[14]] if r[14] else []
                        }
                        reviews_list.append(review_item)
                    except (IndexError, TypeError, ValueError) as e:
                        logger.debug(f"Skipping malformed review entry: {e}")
                        continue

            except Exception as e:
                logger.error(f"Fast Scraper network/parse failure: {str(e)}")
                return []

        return reviews_listimport httpx
import json
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class FastGoogleScraper:
    """
    A high-speed Google Review scraper using direct request emulation.
    Bypasses the overhead of Selenium for 10x faster execution.
    """
    def __init__(self):
        # Using a mobile User-Agent to trigger Google's lightweight AJAX response
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def get_reviews(self, data_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches reviews directly from Google's internal AJAX endpoint.
        
        :param data_id: The unique Google 'feature_id' (e.g., ChIJzVjKHacFGTkR1B_Hr2EH9iA).
        :param limit: Number of reviews to fetch (Google typically caps individual requests at 199).
        """
        # Google's raw AJAX data endpoint
        url = "https://www.google.com/maps/preview/review/listentitiesreviews"
        
        # The 'pb' parameter is a Protobuf-style string that defines the request payload
        # !1i0 = start index, !2i{limit} = count, !3e1 = sort by newest
        params = {
            "authuser": "0",
            "hl": "en",
            "gl": "us",
            "pb": f"!1m1!1s{data_id}!2m2!1i0!2i{limit}!3e1!4m5!4b1!5b1!6b1!7b1!11m1!4b1"
        }

        reviews_list = []
        
        async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
            try:
                response = await client.get(url, params=params)
                
                # Google prefixes their JSON with security characters to prevent hijacking
                if response.text.startswith(")]}'"):
                    clean_text = response.text.replace(")]}'\n", "")
                else:
                    clean_text = response.text

                data = json.loads(clean_text)

                # Drill down into the nested list structure returned by Google
                if not data or len(data) < 3 or data[2] is None:
                    logger.warning(f"No reviews found in response for data_id: {data_id}")
                    return []

                for r in data[2]:
                    try:
                        # Map indices to match your Review model and dashboard requirements
                        review_item = {
                            "review_id": str(r[0]),
                            "rating": int(r[4]),
                            "text": r[3] if r[3] else "",
                            "author_title": r[0][1] if r[0] and len(r[0]) > 1 else "Anonymous User",
                            "author_id": r[6],
                            "author_image": r[0][2] if r[0] and len(r[0]) > 2 else None,
                            # Convert Google's millisecond timestamp to ISO string
                            "review_datetime_utc": datetime.fromtimestamp(r[27]/1000).isoformat() if r[27] else datetime.now().isoformat(),
                            # Check for business owner replies
                            "owner_answer": r[9][1] if r[9] and len(r[9]) > 1 else None,
                            # Extract photo URLs if present
                            "reviews_photos": [p[1][0][6][0] for p in r[14]] if r[14] else []
                        }
                        reviews_list.append(review_item)
                    except (IndexError, TypeError, ValueError) as e:
                        logger.debug(f"Skipping malformed review entry: {e}")
                        continue

            except Exception as e:
                logger.error(f"Fast Scraper network/parse failure: {str(e)}")
                return []

        return reviews_list
