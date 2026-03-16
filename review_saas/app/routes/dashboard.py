# filename: app/routes/dashboard.py

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List, Dict
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Review, Company, Order, Customer, Product
from app.main import templates, get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# ------------------ Helper Functions ------------------

async def get_reviews_summary(session: AsyncSession, company_id: int, start: Optional[str], end: Optional[str]):
    start_dt = datetime.fromisoformat(start) if start else datetime.now() - timedelta(days=365)
    end_dt = datetime.fromisoformat(end) if end else datetime.now()

    res = await session.execute(
        select(Review)
        .where(Review.company_id == company_id)
        .where(Review.review_time.between(start_dt.date(), end_dt.date()))
    )
    reviews: List[Review] = res.scalars().all()

    total_reviews = len(reviews)
    avg_rating = sum(r.rating for r in reviews) / total_reviews if total_reviews else 0
    pos = len([r for r in reviews if r.sentiment_score > 0])
    neu = len([r for r in reviews if r.sentiment_score == 0])
    neg = len([r for r in reviews if r.sentiment_score < 0])

    # Trend data grouped by day
    trend = {}
    for r in reviews:
        day = r.review_time.isoformat()
        trend[day] = trend.get(day, 0) + 1

    # Rating distribution
    rating_dist = {i: 0 for i in range(1, 6)}
    for r in reviews:
        rating_dist[round(r.rating)] += 1

    return {
        "total": total_reviews,
        "avg_rating": avg_rating,
        "positive": pos,
        "neutral": neu,
        "negative": neg,
        "trend": trend,
        "rating_distribution": rating_dist,
        "recent_reviews": [
            {
                "author_name": r.author_name,
                "rating": r.rating,
                "sentiment_score": r.sentiment_score,
                "review_time": r.review_time.isoformat(),
                "text": r.text
            } for r in sorted(reviews, key=lambda x: x.review_time, reverse=True)[:50]
        ]
    }

async def get_customer_summary(session: AsyncSession, company_id: int):
    res = await session.execute(
        select(Customer)
        .where(Customer.company_id == company_id)
    )
    customers: List[Customer] = res.scalars().all()
    total_customers = len(customers)
    new_customers = len([c for c in customers if c.created_at >= datetime.now() - timedelta(days=30)])
    return {
        "total_customers": total_customers,
        "new_customers_last_30_days": new_customers
    }

async def get_product_summary(session: AsyncSession, company_id: int):
    res = await session.execute(
        select(Product)
        .where(Product.company_id == company_id)
    )
    products: List[Product] = res.scalars().all()
    top_products = sorted(products, key=lambda p: p.total_sales, reverse=True)[:5]
    return {
        "total_products": len(products),
        "top_products": [{"name": p.name, "sales": p.total_sales} for p in top_products]
    }

async def get_revenue_summary(session: AsyncSession, company_id: int, start: Optional[str], end: Optional[str]):
    start_dt = datetime.fromisoformat(start) if start else datetime.now() - timedelta(days=365)
    end_dt = datetime.fromisoformat(end) if end else datetime.now()

    res = await session.execute(
        select(Order)
        .where(Order.company_id == company_id)
        .where(Order.created_at.between(start_dt, end_dt))
    )
    orders: List[Order] = res.scalars().all()
    total_revenue = sum(o.total_amount for o in orders)
    avg_order_value = total_revenue / len(orders) if orders else 0
    return {
        "total_revenue": total_revenue,
        "avg_order_value": avg_order_value,
        "total_orders": len(orders)
    }

# ------------------ Dashboard API ------------------

@router.get("/summary", response_class=JSONResponse)
async def dashboard_summary(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    reviews_summary = await get_reviews_summary(session, company_id, start, end)
    customer_summary = await get_customer_summary(session, company_id)
    product_summary = await get_product_summary(session, company_id)
    revenue_summary = await get_revenue_summary(session, company_id, start, end)

    return {
        "reviews": reviews_summary,
        "customers": customer_summary,
        "products": product_summary,
        "revenue": revenue_summary
    }

# ------------------ Dashboard Page ------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "google_api_key": "",  # replace with actual key if needed
            "schema_version": getattr(request.app.state, "schema_version", None),
            "schema_changed": getattr(request.app.state, "schema_changed", False),
            "schema_prev": getattr(request.app.state, "schema_prev", None),
        },
    )
