# FILE: review_saas/app/services/metrics.py
"""
Safest Minimal Metrics Engine
Fixes ImportError by defining ALL required functions.

This file prevents uvicorn startup crash by ensuring
the 8 functions imported by reviews.py all exist.
"""

def aggregate_trends(db, company_id, period, start_date, end_date):
    return {
        "period": period,
        "buckets": []
    }

def aggregate_rating_distribution(db, company_id, start_date, end_date):
    return {
        "distribution": {},
        "total": 0
    }

def compute_rating_sentiment_correlation(db, company_id, start_date, end_date):
    return {
        "correlation": 0.0,
        "n": 0
    }

def aggregate_benchmark(db, company_ids, start_date, end_date):
    return {
        "companies": []
    }

def aggregate_geo_insights(db, company_id, group_by, start_date, end_date):
    return {
        "grouping": group_by,
        "areas": []
    }

def compute_engagement_metrics(db, company_id, start_date, end_date):
    return {
        "review_count": 0,
        "responded_count": 0,
        "response_rate_percent": 0,
        "avg_response_time_hours": None
    }

def build_kpi_snapshot(db, company_id, kpis, start_date, end_date):
    return {
        "kpis": {k: None for k in kpis}
    }

def build_executive_summary(db, company_id, start_date, end_date):
    return {
        "summary": {
            "overall_sentiment": None,
            "rating_trend": [],
            "review_volume": [],
            "key_risks": [],
            "opportunities": []
        }
    }
