# filename: review_saas/app/services/google_reviews.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ──────────────────────────────────────────────────────────────────────────────
# Data models (unchanged fields; only type hints strengthened)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ReviewData:
    review_id: str
    author_name: str
    rating: float
    text: str
    time_created: datetime
    sentiment: Optional[str] = None  # positive/neutral/negative (if upstream provides)
    review_title: Optional[str] = None
    helpful_votes: Optional[int] = 0
    source_platform: Optional[str] = None  # e.g., Google, Yelp
    competitor_name: Optional[str] = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)  # Preserve extra fields


@dataclass
class CompanyReviews:
    company_id: str
    reviews: List[ReviewData] = field(default_factory=list)

    def add_review(self, review: ReviewData):
        self.reviews.append(review)

    def rating_summary(self) -> Dict[str, float]:
        """Return average, min, max, and count of ratings."""
        if not self.reviews:
            return {"average": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        ratings = [float(r.rating or 0.0) for r in self.reviews]
        return {
            "average": sum(ratings) / len(ratings),
            "min": min(ratings),
            "max": max(ratings),
            "count": len(ratings),
        }

    def rating_distribution(self) -> Dict[int, int]:
        """Return count of each rating 1..5 (rounded to nearest int, clamped)."""
        def as_star(v: float) -> int:
            try:
                s = int(round(float(v)))
            except Exception:
                s = 0
            return max(1, min(5, s)) if s else 0

        dist = Counter(as_star(r.rating) for r in self.reviews if r.rating is not None)
        return {i: dist.get(i, 0) for i in range(1, 6)}

    def generate_summary(self) -> str:
        """Light summary (kept compatible with existing callers)."""
        rs = self.rating_summary()
        return (
            f"Total Reviews: {rs['count']}, "
            f"Avg Rating: {rs['average']:.2f}, "
            f"Max Rating: {rs['max']}, "
            f"Min Rating: {rs['min']}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

class OutscraperReviewsService:
    """
    Fetch reviews from Outscraper/Google via an injected `api_client`.

    The client MUST implement:
        get_reviews(place_id: str, limit: int, offset: int, **kwargs) -> dict
    and return a dict with a list under the key "reviews".

    This service supports:
      - Inclusive date filtering (full-day end)
      - Pagination until exhaustion (or Max cap)
      - Multi-entity fetching (competitors)
      - Robust field mapping across vendors
    """
    PAGE_SIZE = 100  # Larger page size for efficiency (adjust per vendor limits)

    def __init__(self, api_client: Any, *, default_kwargs: Optional[Dict[str, Any]] = None):
        self.client = api_client
        self.default_kwargs = default_kwargs or {}

    # ───── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_bounds(start_date: Optional[datetime], end_date: Optional[datetime]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Make date range INCLUSIVE. If date-only or midnight is provided, expand to:
          start -> 00:00:00
          end   -> 23:59:59.999999
        Strip tzinfo to compare naive datetimes consistently.
        """
        s = start_date
        e = end_date

        if s and s.tzinfo:
            s = s.replace(tzinfo=None)
        if e and e.tzinfo:
            e = e.replace(tzinfo=None)

        if s:
            s = datetime.combine(s.date(), time.min)
        if e:
            e = datetime.combine(e.date(), time.max)

        return s, e

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        """
        Convert a variety of fields Outscraper/Google might return into datetime.
        Supported:
          - numeric epoch seconds (int/float)
          - ISO strings (UTC or local)
          - 'YYYY-MM-DD' date strings
        Returns naive datetime (no tzinfo).
        """
        if value is None:
            return None

        # Epoch seconds
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except Exception:
                pass

        # ISO string or 'YYYY-MM-DD'
        if isinstance(value, str):
            # Try ISO
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except Exception:
                pass

            # Try simple date
            try:
                return datetime.strptime(value, "%Y-%m-%d")
            except Exception:
                pass

        return None

    @staticmethod
    def _first(*vals: Any) -> Any:
        """Return the first non-empty/non-null value among provided candidates."""
        for v in vals:
            if v is None:
                continue
            # Treat empty strings as missing
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
        return None

    @staticmethod
    def _as_float(val: Any, default: float = 0.0) -> float:
        try:
            return float(val)
        except Exception:
            return default

    def _to_review(self, row: Dict[str, Any], *, competitor_name: Optional[str] = None) -> Optional[ReviewData]:
        """
        Map a provider-agnostic row -> ReviewData.
        Handles common field name variants from Outscraper/Google exporters.
        """
        # Time fields can be in several keys
        time_val = self._first(
            row.get("time"),
            row.get("timestamp"),
            row.get("review_timestamp"),
            row.get("review_time"),
            row.get("review_datetime_utc"),
            row.get("date"),
            row.get("published_at"),
        )
        time_created = self._coerce_datetime(time_val) or datetime.now()

        # Rating fields
        rating = self._first(
            row.get("rating"),
            row.get("review_rating"),
            row.get("reviews_rating"),
            row.get("stars"),
        )
        rating_f = self._as_float(rating, default=0.0)

        # Author fields
        author = self._first(
            row.get("author_name"),
            row.get("reviewer_name"),
            row.get("user_name"),
            row.get("author"),
            row.get("name"),
        ) or "Anonymous"

        # ID fields
        review_id = self._first(
            row.get("review_id"),
            row.get("id"),
            row.get("google_review_id"),
            row.get("reviewHash"),
        )
        if not review_id:
            # Without a stable ID we can still keep it, but dedupe later in persistence if needed
            review_id = f"noid-{hash((author, time_created.isoformat(), rating_f, row.get('text') or row.get('review_text') or ''))}"

        # Text / title
        text = self._first(row.get("text"), row.get("review_text"), row.get("content")) or ""
        title = self._first(row.get("title"), row.get("review_title"), row.get("summary"))

        # Helpful / likes
        helpful = self._first(
            row.get("helpful_votes"),
            row.get("thumbs_up_count"),
            row.get("likes"),
            row.get("votes"),
        )
        helpful_i = int(self._as_float(helpful, 0.0))

        # Platform/source
        platform = self._first(row.get("platform"), row.get("source")) or "Google"

        # Place/entity name (often available for competitors pages)
        entity_name = self._first(
            competitor_name,
            row.get("competitor_name"),
            row.get("place_name"),
            row.get("location_name"),
            row.get("company_name"),
        )

        return ReviewData(
            review_id=str(review_id),
            author_name=str(author),
            rating=rating_f,
            text=str(text),
            time_created=time_created,
            sentiment=row.get("sentiment"),  # leave as-is if upstream sets it
            review_title=title if title is None or isinstance(title, str) else str(title),
            helpful_votes=helpful_i,
            source_platform=str(platform),
            competitor_name=str(entity_name) if entity_name else None,
            additional_fields=row,  # keep original fields for audit/debug
        )

    # ───── Core fetchers ──────────────────────────────────────────────────────

    def fetch_reviews(
        self,
        place_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_reviews: Optional[int] = None,
        *,
        competitor_name: Optional[str] = None,
        **extra_kwargs: Any,
    ) -> List[ReviewData]:
        """
        Fetch **all** reviews for a single place_id within [start_date, end_date] inclusive.
        - Paginates until exhaustion
        - Strict date filter (inclusive)
        - Optional per-entity cap (max_reviews)
        - `competitor_name` only tags the ReviewData for reporting
        - `extra_kwargs` are passed to the underlying client.get_reviews(...)
        """
        all_reviews: List[ReviewData] = []
        offset = 0
        page = 1

        start_norm, end_norm = self._normalize_bounds(start_date, end_date)

        while True:
            logger.info(
                "Fetching page %s for place_id=%s (offset=%s, page_size=%s)",
                page, place_id, offset, self.PAGE_SIZE
            )

            # Merge service-level and call-level kwargs
            kwargs = {**self.default_kwargs, **extra_kwargs}

            response: Dict[str, Any] = self.client.get_reviews(
                place_id=place_id,
                limit=self.PAGE_SIZE,
                offset=offset,
                **kwargs,
            )

            raw = response.get("reviews", []) or []
            if not raw:
                logger.info("No more reviews returned. Fetch complete after page %s.", page)
                break

            kept_this_page = 0
            for row in raw:
                rd = self._to_review(row, competitor_name=competitor_name)
                if not rd:
                    continue

                # Inclusive date filter
                if start_norm and rd.time_created < start_norm:
                    continue
                if end_norm and rd.time_created > end_norm:
                    continue

                all_reviews.append(rd)
                kept_this_page += 1

                if max_reviews and len(all_reviews) >= max_reviews:
                    logger.info("Reached per-entity max_reviews (%s). Stopping.", max_reviews)
                    break

            logger.info(
                "Page %s: received=%s, kept_in_range=%s, total_kept=%s",
                page, len(raw), kept_this_page, len(all_reviews)
            )

            if max_reviews and len(all_reviews) >= max_reviews:
                break

            # Pagination advance
            offset += self.PAGE_SIZE
            page += 1

            # Stop if vendor signals last page implicitly
            if len(raw) < self.PAGE_SIZE:
                break

        return all_reviews

    def fetch_many(
        self,
        entities: List[Dict[str, Any] | str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_reviews_per_entity: Optional[int] = None,
        **extra_kwargs: Any,
    ) -> Dict[str, List[ReviewData]]:
        """
        Fetch reviews for multiple entities (primary + competitors).

        `entities` can be either:
          - List[str]: each item is a place_id
          - List[dict]: each item may have {"place_id": "...", "name": "Competitor A", ...}

        Returns:
          { place_id: [ReviewData, ...], ... }
        """
        results: Dict[str, List[ReviewData]] = {}

        for ent in entities:
            if isinstance(ent, str):
                pid = ent
                name = None
            elif isinstance(ent, dict):
                pid = str(ent.get("place_id") or "").strip()
                if not pid:
                    logger.warning("Skipping entity without place_id: %r", ent)
                    continue
                name = ent.get("name") or ent.get("competitor_name") or ent.get("label")
            else:
                logger.warning("Unsupported entity type: %r", ent)
                continue

            logger.info("Fetching entity pid=%s name=%s", pid, name or "-")
            items = self.fetch_reviews(
                place_id=pid,
                start_date=start_date,
                end_date=end_date,
                max_reviews=max_reviews_per_entity,
                competitor_name=name,
                **extra_kwargs,
            )
            results[pid] = items

        return results


# ──────────────────────────────────────────────────────────────────────────────
# Public ingestion helpers (backward compatible + multi-entity)
# ──────────────────────────────────────────────────────────────────────────────

def ingest_company_reviews(
    place_id: str,
    company_id: str,
    api_client: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_reviews: Optional[int] = None,  # Default None = fetch everything in range
    **extra_kwargs: Any,
) -> CompanyReviews:
    """
    Backward‑compatible: fetch and return all reviews for a single company.
    Applies INCLUSIVE date range and pagination (no artificial cap unless provided).
    """
    service = OutscraperReviewsService(api_client)

    logger.info(
        "Starting comprehensive review fetch for company %s "
        "(place_id: %s), date range: %s → %s",
        company_id, place_id,
        (start_date.isoformat() if start_date else "any start"),
        (end_date.isoformat() if end_date else "any end"),
    )

    reviews_data = service.fetch_reviews(
        place_id=place_id,
        start_date=start_date,
        end_date=end_date,
        max_reviews=max_reviews,
        **extra_kwargs,
    )

    out = CompanyReviews(company_id=company_id)
    for r in reviews_data:
        out.add_review(r)

    count = len(out.reviews)
    logger.info("Fetch completed: %s reviews in range for company %s (place_id: %s)", count, company_id, place_id)

    if count > 0:
        logger.info("Rating Summary: %s", out.rating_summary())
        logger.info("Rating Distribution: %s", out.rating_distribution())
        logger.info("AI Summary: %s", out.generate_summary())
    else:
        logger.warning("No reviews found in the selected date range.")

    return out


def ingest_multi_company_reviews(
    primary_company_id: str,
    entities: List[Dict[str, Any] | str],
    api_client: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_reviews_per_entity: Optional[int] = None,
    **extra_kwargs: Any,
) -> Dict[str, CompanyReviews]:
    """
    New: fetch reviews for multiple entities (primary + competitors) in one call.

    Args:
      primary_company_id: ID of the primary company in your system (used for logging/grouping).
      entities:
        - List[str] of place_ids, or
        - List[dict] with fields:
            {"place_id": "...", "name": "Competitor A"}  # name is optional
      api_client: provider client (must support get_reviews as described)
      start_date, end_date: inclusive window
      max_reviews_per_entity: per-entity cap (None = unlimited)
      **extra_kwargs: passed to client.get_reviews

    Returns:
      dict mapping place_id -> CompanyReviews (company_id set to primary_company_id for uniformity)
      Each ReviewData carries `competitor_name` if provided/available.
    """
    service = OutscraperReviewsService(api_client)

    logger.info(
        "Starting batch fetch (primary_company_id=%s), entities=%s, window=%s→%s",
        primary_company_id, len(entities),
        (start_date.isoformat() if start_date else "any"),
        (end_date.isoformat() if end_date else "any"),
    )

    batch: Dict[str, CompanyReviews] = {}
    grouped = service.fetch_many(
        entities=entities,
        start_date=start_date,
        end_date=end_date,
        max_reviews_per_entity=max_reviews_per_entity,
        **extra_kwargs,
    )

    # Convert Lists -> CompanyReviews for each place_id
    for pid, rows in grouped.items():
        bucket = CompanyReviews(company_id=primary_company_id)
        for r in rows:
            bucket.add_review(r)
        batch[pid] = bucket

        logger.info(
            "Entity pid=%s name=%s → fetched=%s",
            pid,
            (rows[0].competitor_name if rows else "-"),
            len(rows),
        )

    logger.info("Batch fetch complete: %s entities.", len(batch))
    return batch
