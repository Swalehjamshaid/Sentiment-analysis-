# FILE: review_saas/app/routes/dashboard.py
from __future__ import annotations

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any, Optional, List, Dict, Tuple
from datetime import datetime, date, timedelta
import math

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Company, User, Review  # <-- ensure Review is exposed from app.models
from app.services.analysis import dashboard_payload  # base analytics service

router = APIRouter(tags=["Executive Dashboard"])


# ----------------------------- #
# Helpers (window, parsing, math)
# ----------------------------- #

def _parse_date_safe(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except Exception:
        return None

def _normalize_window(start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    """Default to last 30 days, normalize reversed inputs."""
    end_d = _parse_date_safe(end)
    start_d = _parse_date_safe(start)
    if not end_d and not start_d:
        end_d = date.today()
        start_d = end_d - timedelta(days=30)
    elif start_d and not end_d:
        end_d = start_d + timedelta(days=30)
    elif end_d and not start_d:
        start_d = end_d - timedelta(days=30)
    # normalize if reversed
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d

def _safe_div(n: float, d: float, default: float = 0.0) -> float:
    return (n / d) if d else default

def _pearson(xs: List[float], ys: List[float]) -> float:
    """Simple Pearson correlation (for #10)."""
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    x = xs[:n]
    y = ys[:n]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)

def _star_bucket(rating: float) -> int:
    """Map 0.0-5.0 to 1..5 stars."""
    r = int(round(rating))
    return min(max(r, 1), 5)

def _fmt_pct(p: float) -> str:
    return f"{round(p * 100, 1)}%"


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard_page(
    request: Request,
    company_id: Optional[int] = Query(None, description="Primary company (branch) ID"),
    # #8 Custom Date Filtering
    start: Optional[str] = Query(None, description="ISO Start Date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="ISO End Date (YYYY-MM-DD)"),
    # #11 Comparative Company Benchmarking
    compare_ids: Optional[str] = Query(None, description="Comma-separated IDs for benchmarking"),
    # #1 Multi-Source input (extensible)
    sources: Optional[str] = Query(None, description="Comma-separated sources e.g., google,facebook,appstore"),
    # #7 Trend interval
    interval: Optional[str] = Query("daily", regex="^(daily|weekly|monthly)$"),
    # #17 Customizable KPI selections
    kpis: Optional[str] = Query(None, description="Comma-separated KPI keys to prioritize in UI"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Executive Dashboard
    - #20 Executive Summary
    - #22 RBAC
    - #1..#30 Data contract enrichment matching front-end requirements
    """
    from app.main import templates, common_context

    # ---------- RBAC & Company Access (#22) ----------
    user_role = getattr(current_user, "role", "owner")
    if user_role not in ("owner", "manager", "analyst", "admin"):
        user_role = "owner"

    # Default company selection if none provided: first owned/visible
    selected_company: Optional[Company] = None
    if company_id:
        selected_company = db.query(Company).filter(Company.id == company_id).first()
        if not selected_company:
            raise HTTPException(status_code=404, detail="Selected company not found.")
        # Owners and admins bypass; others must be allowed
        if getattr(selected_company, "owner_id", None) not in (current_user.id, None) and user_role != "admin":
            # You can extend with org/team checks here
            raise HTTPException(status_code=403, detail="Access denied to this company's intelligence.")
    else:
        # Try to auto-pick a company (owned first)
        selected_company = (
            db.query(Company)
            .filter((Company.owner_id == current_user.id) | (user_role == "admin"))
            .order_by(Company.id.asc())
            .first()
        )

    # ---------- Date Window (#8) ----------
    start_date, end_date = _normalize_window(start, end)

    # ---------- Sources Parsing (#1) ----------
    src_list: List[str] = []
    if sources:
        src_list = [s.strip().lower() for s in sources.split(",") if s.strip()]
    else:
        # default: google only; architecture scalable to add others
        src_list = ["google"]

    # ---------- Main Analytics Engine (#3-#7, #21, #24, etc.) ----------
    # We call your existing service and then normalize/enrich to a front-end contract
    base_payload: Dict[str, Any] = {}
    if selected_company:
        try:
            base_payload = dashboard_payload(
                db,
                company_id=selected_company.id,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                sources=src_list,
                interval=interval,
            )
        except TypeError:
            # If dashboard_payload doesn't support the extra kwargs yet,
            # call the legacy signature and enrich locally.
            base_payload = dashboard_payload(
                db,
                company_id=selected_company.id,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )
    else:
        base_payload = {}

    # ---------- Local Enrichment to match UI needs ----------
    # Pull raw reviews for extra analytics (distribution, correlation, response rate, growth)
    def _reviews_qs(_start: date, _end: date):
        q = db.query(Review).filter(
            Review.company_id == selected_company.id,
            func.date(Review.review_date).between(_start, _end),
        )
        if src_list:
            q = q.filter(Review.source.in_(src_list))
        return q

    reviews_in_range: List[Review] = []
    if selected_company:
        reviews_in_range = _reviews_qs(start_date, end_date).order_by(Review.review_date.desc()).all()

    total = len(reviews_in_range)
    avg_rating = round(_safe_div(sum(float(r.rating or 0.0) for r in reviews_in_range), total), 2) if total else 0.0
    # #26 Engagement & Response
    responded = sum(1 for r in reviews_in_range if getattr(r, "responded", False))
    response_rate = _fmt_pct(_safe_div(responded, total))

    # #13 Volume & Growth
    prev_len = (end_date - start_date).days or 1
    prev_start = start_date - timedelta(days=prev_len)
    prev_end = start_date - timedelta(days=1)
    prev_total = 0
    if selected_company:
        prev_total = _reviews_qs(prev_start, prev_end).count()
    growth_rate = _fmt_pct(_safe_div((total - prev_total), prev_total) if prev_total else 0.0)

    # #9 Rating Distribution
    star_bins = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews_in_range:
        star_bins[_star_bucket(float(r.rating or 0))] += 1

    # #4 Emotion Spectrum
    emotion_map: Dict[str, int] = {}
    for r in reviews_in_range:
        key = (r.emotion or "Neutral").title()
        emotion_map[key] = emotion_map.get(key, 0) + 1

    # #5 Aspect Performance (mean score per aspect)
    from collections import defaultdict
    aspect_acc: Dict[str, List[float]] = defaultdict(list)
    for r in reviews_in_range:
        if r.aspects:
            for k, v in r.aspects.items():
                try:
                    aspect_acc[k] += [float(v)]
                except Exception:
                    continue
    aspect_performance = {k: round(_safe_div(sum(v), len(v)), 2) for k, v in aspect_acc.items()}

    # #6 Keywords/Topics (top tokens from payload if present; else shallow extract)
    keywords = base_payload.get("keywords") or base_payload.get("topics") or []
    if not keywords:
        # naive fallback from texts
        from collections import Counter
        import re
        words = []
        for r in reviews_in_range:
            if r.text:
                words += [w.lower() for w in re.findall(r"[A-Za-z]{4,}", r.text)]
        keywords = [w for w, _ in Counter(words).most_common(10)]

    # #10 Correlation between text sentiment_score and star rating
    sentiment_scores = []
    star_scores = []
    for r in reviews_in_range:
        if r.sentiment_score is not None and r.rating is not None:
            sentiment_scores.append(float(r.sentiment_score))
            star_scores.append(float(r.rating))
    correlation = round(_pearson(sentiment_scores, star_scores), 3) if sentiment_scores and star_scores else 0.0

    # #27 Anomaly Detection (simple spike vs mean; you can swap with a real detector)
    # Build simple daily counts
    by_day: Dict[str, int] = {}
    for r in reviews_in_range:
        d = r.review_date.date().isoformat()
        by_day[d] = by_day.get(d, 0) + 1
    daily_vals = list(by_day.values())
    anomaly_detected = False
    if daily_vals:
        mean = sum(daily_vals) / len(daily_vals)
        # 60% spike threshold as a placeholder
        anomaly_detected = any(v > (mean * 1.6) for v in daily_vals)

    # #21 Predictive Insights (naive trend: last 5 vs first 5)
    prediction = "Stable"
    if len(star_scores) >= 10:
        head = sum(star_scores[:5]) / 5.0
        tail = sum(star_scores[-5:]) / 5.0
        if tail - head > 0.05:
            prediction = "Improving"
        elif head - tail > 0.05:
            prediction = "Declining"

    # #20 Executive Summary & Sentiment Score
    pos = sum(1 for r in reviews_in_range if (r.sentiment_category or "").lower() == "positive")
    neg = sum(1 for r in reviews_in_range if (r.sentiment_category or "").lower() == "negative")
    sentiment_score = round(_safe_div((pos - neg), total) * 100.0, 1) if total else 0.0
    status = "Healthy" if sentiment_score >= 15 else ("At Risk" if sentiment_score <= -5 else "Watch")
    risk_level = "Low" if status == "Healthy" else ("High" if status == "At Risk" else "Medium")

    # #15 Alerts (spike, low rating, anomaly, negative trend, keyword watch)
    alerts: List[Dict[str, Any]] = []
    if anomaly_detected:
        alerts.append({"severity": "high", "code": "ANOMALY_SPIKE", "message": "Unusual spike in review activity detected."})
    if avg_rating and avg_rating < 3.2:
        alerts.append({"severity": "high", "code": "LOW_AVG_RATING", "message": "Average rating below 3.2 in the selected window."})
    if prediction == "Declining":
        alerts.append({"severity": "medium", "code": "NEGATIVE_TREND", "message": "Forecast indicates a declining rating trend."})
    # simple keyword watchlist
    watch_terms = {"refund", "rude", "delay", "late", "broken", "fraud"}
    if any(kw in watch_terms for kw in [k.lower() for k in keywords]):
        alerts.append({"severity": "medium", "code": "WATCH_TERMS", "message": "Sensitive terms trending in feedback."})

    # #11 Benchmarking (optional, RBAC gating for competitors if needed)
    benchmarks = []
    if compare_ids:
        try:
            ids = [int(i.strip()) for i in compare_ids.split(",") if i.strip()]
            for b_id in ids:
                if selected_company and b_id == selected_company.id:
                    continue
                other = db.query(Company).filter(Company.id == b_id).first()
                if not other:
                    continue
                # owner/admin visibility check
                if getattr(other, "owner_id", None) not in (current_user.id, None) and user_role != "admin":
                    continue
                # compute quick stats for benchmark window
                b_reviews = (
                    db.query(Review)
                    .filter(
                        Review.company_id == other.id,
                        func.date(Review.review_date).between(start_date, end_date),
                    )
                )
                if src_list:
                    b_reviews = b_reviews.filter(Review.source.in_(src_list))
                b_list = b_reviews.all()
                if not b_list:
                    continue
                b_total = len(b_list)
                b_avg = round(_safe_div(sum(float(x.rating or 0) for x in b_list), b_total), 2)
                b_pos = sum(1 for x in b_list if (x.sentiment_category or "").lower() == "positive")
                b_neg = sum(1 for x in b_list if (x.sentiment_category or "").lower() == "negative")
                b_sent = round(_safe_div((b_pos - b_neg), b_total) * 100.0, 1)
                benchmarks.append({"id": b_id, "name": other.name, "avg_rating": b_avg, "sentiment": b_sent})
        except ValueError:
            # ignore malformed
            pass

    # #12 Geographical Insights (if your schema includes geo per review/branch; fallback to company city)
    geo = base_payload.get("geo") or {}
    if not geo and selected_company and getattr(selected_company, "city", None):
        geo = {selected_company.city: total}

    # #24 Multi-language support breakdown
    language_map: Dict[str, int] = {}
    for r in reviews_in_range:
        lang = (getattr(r, "lang", None) or "en").lower()
        language_map[lang] = language_map.get(lang, 0) + 1

    # #6 Trending Keywords (top-10 from earlier)
    trending_keywords = keywords[:10] if keywords else []

    # #7 Trends (pos/neg/total per interval)
    # Build simple daily buckets; for weekly/monthly, group further
    trend_labels: List[str] = []
    trend_pos: List[int] = []
    trend_neg: List[int] = []
    trend_tot: List[int] = []
    bucket: Dict[str, Dict[str, int]] = {}
    for r in reviews_in_range:
        d = r.review_date.date()
        if interval == "weekly":
            # label as YYYY-WW
            year, week, _ = d.isocalendar()
            key = f"{year}-W{week:02d}"
        elif interval == "monthly":
            key = f"{d.year}-{d.month:02d}"
        else:
            key = d.isoformat()
        if key not in bucket:
            bucket[key] = {"pos": 0, "neg": 0, "tot": 0}
        cat = (r.sentiment_category or "").lower()
        if cat == "positive":
            bucket[key]["pos"] += 1
        elif cat == "negative":
            bucket[key]["neg"] += 1
        bucket[key]["tot"] += 1

    for k in sorted(bucket.keys()):
        trend_labels.append(k)
        trend_pos.append(bucket[k]["pos"])
        trend_neg.append(bucket[k]["neg"])
        trend_tot.append(bucket[k]["tot"])

    # ---------- Build the Front-End Contract ----------
    ui_payload: Dict[str, Any] = {
        "company": {
            "id": selected_company.id if selected_company else None,
            "name": selected_company.name if selected_company else None,
            "city": getattr(selected_company, "city", None) if selected_company else None,
            "last_sync": getattr(selected_company, "last_sync", None).isoformat() if (selected_company and getattr(selected_company, "last_sync", None)) else None,
            "sources_active": src_list,
            # #23 API health (fallback to Healthy; if you track it in base_payload, use that)
            "api_health": base_payload.get("company", {}).get("api_health", "Healthy"),
        },
        "window": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "interval": interval,
        },
        "metrics": {
            # #13 Volume
            "total_volume": total,
            # #9 Distribution
            "rating_distribution": {
                "labels": ["1★", "2★", "3★", "4★", "5★"],
                "data": [star_bins[1], star_bins[2], star_bins[3], star_bins[4], star_bins[5]],
            },
            # #26 Engagement
            "response_rate": response_rate,
            # #27 Anomaly
            "anomaly_detected": anomaly_detected,
            # #17 KPI baseline
            "avg_rating": avg_rating,
            "review_growth_rate": growth_rate,
            # #10 Correlation
            "sentiment_rating_correlation": correlation,
            # #24 Languages
            "languages": language_map,
        },
        "visuals": {
            # #7 Trend
            "sentiment_trend": {
                "labels": trend_labels,
                "datasets": {
                    "positive": trend_pos,
                    "negative": trend_neg,
                    "total": trend_tot,
                },
            },
            # #4 Emotions
            "emotion_map": emotion_map,
            # #5 Aspects
            "aspect_performance": aspect_performance,
            # #12 Geo
            "geo": geo,
            # #6 Keywords
            "trending_keywords": trending_keywords,
        },
        "executive_summary": {
            # #20 Exec snapshot keys used by your UI
            "sentiment_score": sentiment_score,
            "status": status,
            "prediction": prediction,  # #21
            "risk_level": risk_level,
            # optional extra copy (used by some templates)
            "headline": f"{sentiment_score}% Sentiment • {status}",
        },
        "drill_down": {
            # #16 Drill-down review feed (client-side pagination in your template)
            "recent_reviews": [{
                "id": r.id,
                "reviewer_name": r.reviewer_name or "Verified Customer",
                "source": (r.source or "google").lower(),
                "rating": int(round(float(r.rating or 0))),  # UI shows X.0 ★
                "emotion": (r.emotion or "Neutral").title(),
                "lang": (getattr(r, "lang", None) or "en").lower(),
                "text": r.text or "",
                "aspects": r.aspects or {},  # dict of aspect -> score
                "sentiment_category": r.sentiment_category or "Neutral",
                "sentiment_score": r.sentiment_score if r.sentiment_score is not None else None,
                "review_date": r.review_date.isoformat(),
                "responded": bool(getattr(r, "responded", False)),
                "response_time_seconds": getattr(r, "response_time_seconds", None),
            } for r in reviews_in_range[:250]],
        },
        # #11 Benchmarking
        "benchmarks": benchmarks,
        # #15 Alerts list for toasts/banners
        "alerts": alerts,
        # #17 Chosen KPIs (optional)
        "kpis": [k.strip() for k in kpis.split(",")] if kpis else ["avg_rating", "sentiment_score", "response_rate", "review_growth_rate"],
        # Convenience flags for the front-end to toggle features
        "feature_flags": {
            "multi_source": True,      # #1
            "real_time": True,         # #2 (actual WS/SSE would be in another route)
            "exporting": True,         # #19 (hook to export endpoints)
            "geo_enabled": True,       # #12
            "competitor_benchmark": True,  # #18
        },
    }

    # Merge through base_payload (if it already provides some sections)
    # priority to enriched ui_payload keys to keep contract consistent
    def deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(b)
        for k, v in a.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = deep_merge(v, out[k])
            else:
                out[k] = v
        return out

    payload = deep_merge(ui_payload, base_payload or {})

    # ---------- UI Context ----------
    context = common_context(request)
    context.update({
        "dashboard_payload": payload,
        "selected_company": selected_company,
        "user_role": user_role,
        "filters": {"start": start_date.isoformat(), "end": end_date.isoformat(), "interval": interval, "sources": src_list},
        # Simple health surface (#23)
        "api_health": payload.get("company", {}).get("api_health", "Healthy"),
        # Optional export endpoints for #19 (front button can call these)
        "export_endpoints": {
            "pdf": f"/api/exports/executive.pdf?company_id={selected_company.id if selected_company else ''}&start={start_date}&end={end_date}",
            "csv": f"/api/exports/reviews.csv?company_id={selected_company.id if selected_company else ''}&start={start_date}&end={end_date}",
            "xlsx": f"/api/exports/reviews.xlsx?company_id={selected_company.id if selected_company else ''}&start={start_date}&end={end_date}",
        },
    })

    return templates.TemplateResponse("dashboard.html", context)
