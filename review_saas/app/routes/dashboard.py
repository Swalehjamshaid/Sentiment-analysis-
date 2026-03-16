# filename: app/routes/dashbord.py

from __future__ import annotations
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])

# -------------------- Text utils & domain dictionaries --------------------

STOPWORDS = {
    "the","a","an","and","or","but","if","while","with","at","by","for","to","from",
    "on","in","of","is","are","was","were","be","been","it","this","that","as","we",
    "you","they","he","she","i","me","my","our","your","their","so","very","too",
    "not","no","yes","can","could","would","should","will","just","there","here",
}

POSITIVE_WORDS = {
    "good","great","excellent","amazing","awesome","fast","quick","helpful","friendly",
    "clean","tasty","fresh","professional","nice","kind","best","love","lovely","super",
    "satisfied","happy","polite","responsive","perfect","recommend","enjoyed","smooth",
}

NEGATIVE_WORDS = {
    "bad","terrible","awful","slow","rude","dirty","cold","stale","late","expensive",
    "overpriced","worst","horrible","disappointed","unprofessional","noisy","crowded",
    "wait","waiting","delay","delayed","broken","poor","dirty","smelly","leaky","refund",
}

EMOTIONS = {
    "happy": {"happy","glad","pleased","delighted","satisfied","great","love","amazing"},
    "angry": {"angry","furious","outraged","mad","enraged"},
    "frustrated": {"frustrated","annoyed","irritated","upset"},
    "satisfied": {"satisfied","content","pleased"},
}

COMPLAINT_CATEGORIES = {
    "service": {"service","response","support","wait","waiting","delay","slow","rude","unhelpful"},
    "price": {"price","expensive","overpriced","cost","charges","fees"},
    "staff behavior": {"staff","waiter","employee","cashier","manager","rude","impolite","attitude"},
    "delivery": {"delivery","late","delay","logistics","shipping","courier"},
    "cleanliness": {"clean","dirty","hygiene","smell","trash","sticky","unclean"},
}

SERVICE_KEYWORDS = {"service","support","response","helpful","rude","wait","waiting","queue","manager","staff"}
STAFF_KEYWORDS = {"staff","waiter","employee","cashier","manager","crew","team"}
PRODUCT_HINTS = {"latte","coffee","burger","pizza","fries","sandwich","tea","cake","dessert","meal","combo","sauce"}
SPAM_KEYWORDS = {"promo","discount code","bit.ly","http://","https://","free money","giveaway"}
REPEATED_TEXT_MIN = 3  # threshold to flag duplicate/similar text across reviews

TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9]+")

def tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_SPLIT.split(text or "") if t and len(t) > 1]

def significant_tokens(text: str) -> List[str]:
    toks = tokenize(text)
    return [t for t in toks if t not in STOPWORDS and not t.isdigit()]

def rating_to_sentiment_score(r: Optional[float]) -> float:
    if r is None:
        return 0.0
    r = max(1.0, min(5.0, float(r)))
    return round((r - 3.0) / 2.0, 2)  # -1..1

def sentiment_label(score: float) -> str:
    if score > 0.15:
        return "Positive"
    if score < -0.15:
        return "Negative"
    return "Neutral"

# -------------------- Pydantic payloads --------------------

class InsightsRequest(BaseModel):
    company_id: int
    start: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    end: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    limit: int = Field(default=500, ge=1, le=5000)

class ResponseSuggestRequest(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    text: str

# -------------------- Core computation --------------------

@dataclass
class ReviewRow:
    rating: Optional[int]
    text: str
    author_name: Optional[str]
    dt: Optional[datetime]
    sentiment_score: Optional[float]

def load_reviews(session: AsyncSession, company_id: int, start_d: date, end_d: date, limit: int) -> List[ReviewRow]:
    """Synchronous facade used inside endpoint (we await in the endpoint)."""
    raise NotImplementedError("Use _aload_reviews async version")

async def _aload_reviews(session: AsyncSession, company_id: int, start_d: date, end_d: date, limit: int) -> List[ReviewRow]:
    q = (
        select(Review)
        .where(
            and_(
                Review.company_id == company_id,
                Review.google_review_time.is_not(None),
                Review.google_review_time >= datetime.combine(start_d, datetime.min.time()),
                Review.google_review_time <= datetime.combine(end_d, datetime.max.time()),
            )
        )
        .order_by(Review.google_review_time.desc())
        .limit(limit)
    )
    res = await session.execute(q)
    rows = res.scalars().all()
    out: List[ReviewRow] = []
    for r in rows:
        out.append(
            ReviewRow(
                rating=r.rating,
                text=r.text or "",
                author_name=r.author_name,
                dt=r.google_review_time,
                sentiment_score=r.sentiment_score,
            )
        )
    return out

def detect_emotions(tokens: List[str]) -> List[str]:
    hits = set()
    for emotion, words in EMOTIONS.items():
        if any(w in tokens for w in words):
            hits.add(emotion)
    return sorted(hits)

def categorize_complaints(tokens: List[str]) -> List[str]:
    cats = []
    for name, words in COMPLAINT_CATEGORIES.items():
        if any(w in tokens for w in words):
            cats.append(name)
    return cats

def topic_buckets(tokens: List[str]) -> List[str]:
    """Simple topic grouping via keyword maps (no ML dependencies)."""
    topics = []
    # You can expand keyword sets for richer grouping
    TOPIC_MAP = {
        "Food quality": {"tasty","fresh","stale","cold","hot","portion","quality","taste","food"},
        "Customer service": {"service","support","rude","helpful","queue","wait","manager","staff"},
        "Pricing": {"price","expensive","cheap","overpriced","value","cost"},
        "Atmosphere": {"music","noisy","quiet","ambience","clean","dirty","smell","decor"},
    }
    for tname, kws in TOPIC_MAP.items():
        if any(w in tokens for w in kws):
            topics.append(tname)
    return topics

def service_quality_score(tokens: List[str], pos_words: set, neg_words: set) -> int:
    """Score 0-100 using service-related mentions (simple ratio)."""
    service_mentions = [t for t in tokens if t in SERVICE_KEYWORDS]
    if not service_mentions:
        return 50  # neutral when no signal
    pos = sum(1 for t in service_mentions if t in pos_words)
    neg = sum(1 for t in service_mentions if t in neg_words)
    total = pos + neg if (pos + neg) > 0 else len(service_mentions)
    raw = (pos - neg) / max(1, total)
    return int(round((raw + 1) * 50))  # map -1..1 => 0..100

def staff_performance(tokens: List[str]) -> Tuple[float, float]:
    mentions = [t for t in tokens if t in STAFF_KEYWORDS]
    if not mentions:
        return (0.0, 0.0)
    pos = sum(1 for t in mentions if t in POSITIVE_WORDS)
    neg = sum(1 for t in mentions if t in NEGATIVE_WORDS)
    total = max(1, len(mentions))
    return (round(100 * pos / total, 1), round(100 * neg / total, 1))

def detect_products(tokens: List[str]) -> List[Tuple[str, int]]:
    candidates = [t for t in tokens if t in PRODUCT_HINTS or (t.istitle() and len(t) > 2)]
    counts = Counter(candidates)
    return counts.most_common(5)

def reputation_score(avg_rating: float, avg_sentiment: float, complaint_ratio: float) -> int:
    """
    0..100 from rating (60%), sentiment (30%), complaints (10% penalty).
    complaint_ratio in 0..1 where 1 means all are complaints.
    """
    rating_component = (avg_rating / 5.0) * 60.0
    sentiment_component = ((avg_sentiment + 1) / 2.0) * 30.0
    penalty = complaint_ratio * 10.0
    return max(0, min(100, int(round(rating_component + sentiment_component - penalty))))

def csat(positives: int, total: int) -> float:
    return round((positives / total) * 100, 1) if total > 0 else 0.0

def time_of_day_bucket(dt: datetime) -> str:
    h = dt.hour
    if 6 <= h < 12:
        return "Morning"
    if 12 <= h < 17:
        return "Afternoon"
    if 17 <= h < 22:
        return "Evening"
    return "Night"

def week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def is_negative(tokens: List[str], score: float) -> bool:
    return score < -0.15 or any(w in NEGATIVE_WORDS for w in tokens)

def fake_review_flags(texts: List[str], ratings: List[Optional[int]]) -> Dict[str, any]:
    flags = {}
    # Repeated text detection
    norm_lines = [" ".join(significant_tokens(t)) for t in texts]
    counts = Counter(norm_lines)
    repeated = [t for t, c in counts.items() if c >= REPEATED_TEXT_MIN and len(t) > 10]
    if repeated:
        flags["repeated_text_patterns"] = repeated[:5]

    # Unusual rating patterns: many extremes with similar text
    extreme_idxs = [i for i, r in enumerate(ratings) if r in (1, 5)]
    if len(extreme_idxs) >= max(3, len(ratings) // 4):
        flags["extreme_rating_bias"] = True

    # Spam keywords
    spam_hits = [t for t in texts if any(kw in t.lower() for kw in SPAM_KEYWORDS)]
    if spam_hits:
        flags["spam_keyword_hits"] = min(len(spam_hits), 10)

    flags["suspected"] = bool(flags)
    return flags

def negative_spike_alert(weekly_neg_counts: List[Tuple[str, int]]) -> Optional[str]:
    """
    Detect sudden spike vs previous week (simple % increase).
    """
    if len(weekly_neg_counts) < 2:
        return None
    w_prev, c_prev = weekly_neg_counts[-2]
    w_now, c_now = weekly_neg_counts[-1]
    if c_prev == 0 and c_now >= 3:
        return f"Alert: Negative reviews spiked to {c_now} in {w_now}"
    if c_prev > 0 and c_now > c_prev:
        inc = int(round(100 * (c_now - c_prev) / c_prev))
        if inc >= 30:
            return f"Alert: Negative reviews increased {inc}% in {w_now}"
    return None

def improvement_suggestions(pain_points: List[str], service_score: int, staff_neg_pct: float) -> List[str]:
    recs = []
    if "service" in pain_points or service_score < 60:
        recs.append("Improve response time and queue handling to reduce service-related complaints.")
    if "price" in pain_points:
        recs.append("Consider transparent pricing or value offers to address price sensitivity.")
    if "staff behavior" in pain_points or staff_neg_pct > 20:
        recs.append("Train frontline staff on empathy and conflict resolution; establish quick escalation paths.")
    if "cleanliness" in pain_points:
        recs.append("Tighten cleaning schedules and spot checks during peak hours.")
    if not recs:
        recs.append("Maintain consistency—current operations appear stable. Continue monitoring weekly trends.")
    return recs

def response_suggestion(rating: Optional[int], text: str) -> str:
    base_apology = "Thank you for your feedback. We’re sorry for the inconvenience you experienced."
    base_thanks = "Thank you for your kind words! We’re delighted you had a great experience."
    base_neutral = "Thanks for taking the time to share your thoughts. We appreciate your feedback."
    ask_more = "If you’re open to it, please share more details at support@example.com so we can make this right."
    improve = "We’ll share this with our team and take immediate steps to improve."
    excite = "We look forward to serving you again soon!"

    if rating is not None:
        if rating <= 2:
            return f"{base_apology} {improve} {ask_more}"
        if rating == 3:
            return f"{base_neutral} {improve}"
        if rating >= 4:
            return f"{base_thanks} {excite}"
    # Fallback to sentiment from text keywords
    toks = significant_tokens(text)
    if any(w in NEGATIVE_WORDS for w in toks):
        return f"{base_apology} {improve} {ask_more}"
    if any(w in POSITIVE_WORDS for w in toks):
        return f"{base_thanks} {excite}"
    return f"{base_neutral}"

# -------------------- Endpoint: Insights --------------------

@router.get("/insights")
async def ai_insights(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    comp = await session.get(Company, company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")

    start_d = datetime.fromisoformat(start).date() if start else date.min
    end_d = datetime.fromisoformat(end).date() if end else date.max

    revs = await _aload_reviews(session, company_id, start_d, end_d, limit)

    total = len(revs)
    if total == 0:
        return {
            "total": 0,
            "message": "No reviews found in range.",
            "metrics": {},
        }

    # Precompute fields
    pos_count = neu_count = neg_count = 0
    all_tokens: List[str] = []
    emotion_counts = Counter()
    complaint_counts = Counter()
    topic_counts = Counter()
    time_of_day_stats = Counter()
    weekly_counts = Counter()
    weekly_neg_counts = Counter()
    author_counts = Counter()

    sentiments: List[float] = []
    ratings: List[Optional[int]] = []
    texts: List[str] = []

    # For competitor benchmark (use cross-company averages)
    # Compute later via a separate query to avoid mixing
    for r in revs:
        # derive score
        score = r.sentiment_score if r.sentiment_score is not None else rating_to_sentiment_score(r.rating)
        sentiments.append(score)
        label = sentiment_label(score)
        if label == "Positive":
            pos_count += 1
        elif label == "Negative":
            neg_count += 1
        else:
            neu_count += 1

        toks = significant_tokens(r.text)
        all_tokens.extend(toks)

        # emotions
        for emo in detect_emotions(toks):
            emotion_counts[emo] += 1

        # complaints
        for cat in categorize_complaints(toks):
            complaint_counts[cat] += 1

        # topics
        for tp in topic_buckets(toks):
            topic_counts[tp] += 1

        # time-of-day
        if r.dt:
            bucket = time_of_day_bucket(r.dt)
            time_of_day_stats[bucket] += 1
            wk = week_key(r.dt)
            weekly_counts[wk] += 1
            if label == "Negative":
                weekly_neg_counts[wk] += 1

        if r.author_name:
            author_counts[r.author_name] += 1

        ratings.append(r.rating)
        texts.append(r.text)

    avg_rating = round(sum((rr or 0) for rr in ratings) / total, 2) if total else 0.0
    avg_sentiment = round(sum(sentiments) / total, 3)

    # 1 — Sentiment labels already computed above
    # 2 — Emotions
    emotions_out = dict(emotion_counts)
    # 3 — Complaint categories
    complaints_out = dict(complaint_counts)
    # 4 — Keyword intelligence
    top_keywords = [w for w, c in Counter(all_tokens).most_common(20)]
    # 5 — Topic clustering
    topics_out = dict(topic_counts)

    # 6 — Reputation score
    complaint_total = sum(complaint_counts.values())
    complaint_ratio = (complaint_total / total) if total else 0.0
    reputation = reputation_score(avg_rating, avg_sentiment, complaint_ratio)

    # 7 — CSAT
    csat_score = csat(pos_count, total)

    # 8 — Negative review alert
    weekly_neg_sorted = sorted(weekly_neg_counts.items())  # list of (week, count)
    neg_alert = negative_spike_alert(weekly_neg_sorted) if weekly_neg_sorted else None

    # 9 — Competitor benchmark = avg rating of OTHER companies in DB
    #    (if no other companies or no ratings in range, show None)
    other_avg_rating = None
    # Efficient aggregate over other companies in date range
    res = await session.execute(
        select(func.avg(Review.rating))
        .join(Company, Company.id == Review.company_id)
        .where(
            and_(
                Company.id != company_id,
                Review.google_review_time.is_not(None),
                Review.google_review_time >= datetime.combine(start_d, datetime.min.time()),
                Review.google_review_time <= datetime.combine(end_d, datetime.max.time()),
            )
        )
    )
    val = res.scalar_one_or_none()
    if val is not None:
        other_avg_rating = round(float(val), 2)

    # 10 — Review response suggestions (exposed via separate POST; here we include examples)
    example_suggestions = {
        "negative": "Thank you for your feedback. We’re sorry for the inconvenience you experienced. We’ll share this with our team and take immediate steps to improve. If you’re open to it, please share more details at support@example.com so we can make this right.",
        "neutral": "Thanks for taking the time to share your thoughts. We appreciate your feedback. We’ll share this with our team and take immediate steps to improve.",
        "positive": "Thank you for your kind words! We’re delighted you had a great experience. We look forward to serving you again soon!",
    }

    # 11 — Fake review detection
    fake_flags = fake_review_flags(texts, ratings)

    # 12 — Customer loyalty detection
    repeat_customers = [{ "author_name": a, "count": c } for a, c in author_counts.items() if c >= 2]

    # 13 — Time-of-day sentiment analysis
    tod_order = ["Morning","Afternoon","Evening","Night"]
    tod_stats = {k: time_of_day_stats.get(k, 0) for k in tod_order}

    # 14 — Weekly trend analysis
    weekly_sorted = sorted(weekly_counts.items())
    weekly_trend = [{"week": w, "reviews": c} for w, c in weekly_sorted]

    # 15 — Service quality score (0..100)
    svc_score = service_quality_score(all_tokens, POSITIVE_WORDS, NEGATIVE_WORDS)

    # 16 — Staff performance insights
    staff_pos_pct, staff_neg_pct = staff_performance(all_tokens)
    staff_insights = {
        "positive_staff_mentions_pct": staff_pos_pct,
        "negative_staff_mentions_pct": staff_neg_pct,
    }

    # 17 — Product feedback detection
    top_products = [{"product": p, "count": cnt} for p, cnt in detect_products(all_tokens)]

    # 18 — Review heatmap (day_of_week x hour bucket)
    # Build simple density map
    heatmap = defaultdict(lambda: defaultdict(int))  # heatmap[day][hour] = count
    for r in revs:
        if not r.dt:
            continue
        day = r.dt.strftime("%a")  # Mon..Sun
        hour = r.dt.hour
        heatmap[day][hour] += 1
    review_heatmap = {
        day: dict(heatmap[day]) for day in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    }

    # 19 — Customer pain points (top complaint categories sorted)
    pain_points_sorted = sorted(complaint_counts.items(), key=lambda x: x[1], reverse=True)
    pain_points = [name for name, _ in pain_points_sorted[:5]]

    # 20 — AI Business Improvement Suggestions
    suggestions = improvement_suggestions(pain_points, svc_score, staff_neg_pct)

    return {
        "total": total,
        "overview": {
            "avg_rating": avg_rating,
            "avg_sentiment": avg_sentiment,
            "sentiment_breakdown": {
                "positive": pos_count,
                "neutral": neu_count,
                "negative": neg_count,
            },
            "csat": csat_score,  # %
            "reputation_score": reputation,  # 0..100
        },
        "nlp": {
            "top_keywords": top_keywords,
            "emotions": emotions_out,
            "topics": topics_out,
            "complaints": complaints_out,
        },
        "trends": {
            "time_of_day": tod_stats,
            "weekly": weekly_trend,
            "negative_alert": neg_alert,
            "heatmap": review_heatmap,
        },
        "benchmarks": {
            "your_rating": avg_rating,
            "competitor_average_rating": other_avg_rating,
        },
        "quality": {
            "service_score": svc_score,
            "staff_performance": staff_insights,
            "products_top": top_products,
            "fake_review_detection": fake_flags,
            "repeat_customers": repeat_customers,
        },
        "business": {
            "pain_points": pain_points,
            "improvement_suggestions": suggestions,
        },
        "examples": {
            "response_suggestions": example_suggestions
        }
    }

# -------------------- Endpoint: Response Suggestion --------------------

@router.post("/response_suggestion")
async def ai_response_suggestion(payload: ResponseSuggestRequest):
    return {
        "suggestion": response_suggestion(payload.rating, payload.text or "")
    }
