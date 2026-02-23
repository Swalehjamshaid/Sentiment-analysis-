# ─────────────────────────────────────────────────────────────
# Core analysis logic
# ─────────────────────────────────────────────────────────────
def _daily_buckets_range(reviews: List[Review], start: datetime, end: datetime) -> List[Dict]:
    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_day = end.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
    days_diff = (end_day.date() - start_day.date()).days + 1
    if days_diff < 1:
        return []

    buckets: Dict[str, Dict] = {}
    for i in range(days_diff):
        d = (start_day + timedelta(days=i)).date().isoformat()
        buckets[d] = {"date": d, "ratings": [], "scores": [], "counts": {"Positive": 0, "Neutral": 0, "Negative": 0}}

    for r in reviews:
        dt = _parse_review_date(r)
        if not dt or dt < start_day or dt > end_day:
            continue
        day_str = dt.date().isoformat()
        lbl = classify_sentiment(r.rating)
        score = 1.0 if lbl == "Positive" else -1.0 if lbl == "Negative" else 0.0
        buckets[day_str]["ratings"].append(r.rating or 0)
        buckets[day_str]["scores"].append(score)
        buckets[day_str]["counts"][lbl] += 1

    return [
        {
            "date": d,
            "avg_rating": round(sum(b["ratings"]) / len(b["ratings"]), 2) if b["ratings"] else None,
            "sent_score": round(sum(b["scores"]) / len(b["scores"]), 3) if b["scores"] else 0.0,
            **b["counts"]
        }
        for d, b in sorted(buckets.items())
    ]


def get_review_summary_data(
    reviews: List[Review],
    company: Company,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    include_aspects: bool = True
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = start or (now - timedelta(days=180))
    end = end or now
    if end < start:
        start, end = end, start

    windowed = [r for r in reviews if (dt := _parse_review_date(r)) and start <= dt <= end]

    if not windowed:
        return {
            "company_name": getattr(company, "name", f"ID {company.id}"),
            "total_reviews": 0,
            "avg_rating": 0.0,
            "risk_score": 0,
            "risk_level": "Low",
            "trend_data": [],
            "trend": {"signal": "insufficient_data", "delta": 0.0},
            "sentiments": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "ai_recommendations": [],
            "daily_series": [],
            "aspects": [],
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "payload_version": "3.3"
        }

    sentiments: Dict[str, int] = {"Positive": 0, "Neutral": 0, "Negative": 0}
    trend_data: Dict[str, List[float]] = defaultdict(list)
    neg_keywords: List[str] = []
    aspect_counter: Counter = Counter()

    for r in windowed:
        sent = classify_sentiment(r.rating)
        sentiments[sent] += 1
        if r.text:
            toks = extract_keywords(r.text)
            if sent == "Negative":
                neg_keywords.extend(toks)
            if include_aspects:
                for a in map_aspects(toks):
                    aspect_counter[a] += 1
        dt = _parse_review_date(r)
        if dt:
            trend_data[dt.strftime("%Y-%m")].append(r.rating or 0)

    trend_list = [{"month": m, "avg_rating": round(sum(v)/len(v), 2)} for m, v in sorted(trend_data.items())]

    trend = {"signal": "insufficient_data", "delta": 0.0}
    if len(trend_list) >= 3:
        last = trend_list[-1]["avg_rating"]
        first = trend_list[0]["avg_rating"]
        delta = round(last - first, 2)
        if len(trend_list) >= 6:
            last3 = sum(x["avg_rating"] for x in trend_list[-3:]) / 3
            prev3 = sum(x["avg_rating"] for x in trend_list[-6:-3]) / 3
            delta = round(last3 - prev3, 2)
        if delta <= -0.3:
            trend = {"signal": "declining", "delta": delta}
        elif delta >= 0.3:
            trend = {"signal": "improving", "delta": delta}
        else:
            trend = {"signal": "stable", "delta": delta}

    total = len(windowed)
    rated = [r.rating for r in windowed if r.rating is not None]
    avg_rating = round(sum(rated)/len(rated), 2) if rated else 0.0

    neg_share = sentiments["Negative"] / total if total else 0
    risk_score = round(neg_share * 100 + (15 if trend["signal"] == "declining" else 0), 1)
    risk_level = "High" if risk_score >= 45 else "Medium" if risk_score >= 20 else "Low"

    recs = []
    seen = set()
    for kw, count in Counter(neg_keywords).most_common(6):
        if kw in seen:
            continue
        seen.add(kw)
        recs.append({
            "area": kw,
            "count": count,
            "priority": "High" if count >= 5 else "Medium",
            "action": _action_for_keyword(kw)
        })

    daily_series = _daily_buckets_range(windowed, start, end)
    aspects = [{"aspect": k, "count": v} for k, v in aspect_counter.most_common()]

    return {
        "company_name": getattr(company, "name", f"ID {company.id}"),
        "total_reviews": total,
        "avg_rating": avg_rating,
        "sentiments": sentiments,
        "trend_data": trend_list,
        "trend": trend,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "ai_recommendations": recs,
        "daily_series": daily_series,
        "aspects": aspects,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "payload_version": "3.3"
    }


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────
@router.get("/google/places")
def google_places_search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=10)):
    if not gmaps:
        return {"ok": False, "reason": "Google Places client not available"}
    try:
        resp = gmaps.find_place(
            input=q,
            input_type="textquery",
            fields=["place_id", "name", "formatted_address"]
        )
        candidates = (resp.get("candidates") or [])[:limit]
        items = []
        for c in candidates:
            pid = c.get("place_id")
            detail = _enrich_place_detail(pid) if pid else {}
            items.append({
                "name": detail.get("name") or c.get("name"),
                "place_id": pid,
                "formatted_address": detail.get("formatted_address") or c.get("formatted_address"),
                "city": detail.get("city"),
                "country": detail.get("country"),
                "rating": detail.get("rating"),
                "user_ratings_total": detail.get("user_ratings_total"),
                "location": detail.get("location"),
                "website": detail.get("website"),
                "international_phone_number": detail.get("international_phone_number"),
            })
        return {"ok": True, "items": items}
    except Exception as e:
        logger.error(f"Places search failed: {e}")
        return {"ok": False, "reason": "external_api_error"}


@router.get("/summary/{company_id}")
def reviews_summary(
    company_id: int,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    include_aspects: bool = Query(True),
    db: Session = Depends(get_db)
):
    cache_key = (company_id, start, end if end else None)
    now_ts = time.time()

    if SUMMARY_TTL_SECONDS > 0:
        cached = _summary_cache.get(cache_key)
        if cached and (now_ts - cached[0] < SUMMARY_TTL_SECONDS):
            return cached[1]

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    start_dt = _parse_date_param(start, as_end=False) if start else None
    end_dt = _parse_date_param(end, as_end=True) if end else None

    reviews = db.query(Review).filter(Review.company_id == company_id)
    if start_dt:
        reviews = reviews.filter(Review.review_date >= start_dt)
    if end_dt:
        reviews = reviews.filter(Review.review_date <= end_dt)

    reviews_list = reviews.order_by(Review.review_date.desc()).limit(8000).all()
    result = get_review_summary_data(reviews_list, company, start_dt, end_dt, include_aspects=include_aspects)

    if SUMMARY_TTL_SECONDS > 0:
        _summary_cache[cache_key] = (now_ts, result)

    return result


@router.get("/list/{company_id}")
def list_reviews(
    company_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    rating: Optional[int] = Query(None, ge=1, le=5),
    q: Optional[str] = Query(None, min_length=2),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    start_dt = _parse_date_param(start, as_end=False) if start else None
    end_dt = _parse_date_param(end, as_end=True) if end else None

    qry = db.query(Review).filter(Review.company_id == company_id)
    if rating:
        qry = qry.filter(Review.rating == rating)
    if q:
        s = f"%{q.lower().strip()}%"
        qry = qry.filter(Review.text.ilike(s))
    if start_dt:
        qry = qry.filter(Review.review_date >= start_dt)
    if end_dt:
        qry = qry.filter(Review.review_date <= end_dt)

    qry = qry.order_by(Review.review_date.asc() if order == "asc" else Review.review_date.desc())
    total = qry.count()
    items = qry.offset((page - 1) * limit).limit(limit).all()

    data = [
        {
            "id": r.id,
            "rating": r.rating,
            "text": r.text,
            "reviewer_name": r.reviewer_name,
            "review_date": (_parse_review_date(r) or datetime.now(timezone.utc)).isoformat(),
        }
        for r in items
    ]
    return {"total": total, "page": page, "limit": limit, "items": data}


@router.get("/sync/{company_id}")
def reviews_sync(company_id: int, db: Session = Depends(get_db), max_reviews: int = Query(60, ge=1, le=200)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    if not gmaps:
        return {"ok": False, "reason": "Google client unavailable"}

    added = fetch_and_save_reviews_places(company, db, max_reviews=max_reviews)
    if SUMMARY_TTL_SECONDS > 0:
        keys_to_drop = [k for k in _summary_cache.keys() if k[0] == company_id]
        for k in keys_to_drop:
            _summary_cache.pop(k, None)
    return {"ok": True, "added": added, "message": "Sync completed"}


@router.get("/diagnostics")
def reviews_diagnostics():
    return {
        "googlemaps_imported": googlemaps is not None,
        "places_client_active": gmaps is not None,
        "api_key_source": api_src,
        "api_token_configured": bool(API_TOKEN),
        "default_window_days": 180,
        "summary_cache_ttl": SUMMARY_TTL_SECONDS
    }
