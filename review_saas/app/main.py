# FILE: app/main.py
import os
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import secrets

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from markupsafe import Markup

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.db import init_db, get_db
from app.models import Company
from app.services.rbac import get_current_user

from app.routes import auth, companies, reviews, reply, reports, dashboard
from app.routes.maps_routes import router as maps_router
from app.routes.activity import router as activity_router
from app.routes.insights import router as insights_router

from app.dependencies import manager

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
if not TEMPLATE_DIR.exists():
    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
    STATIC_DIR = PROJECT_ROOT / "app" / "static"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_saas")

class Settings:
    APP_NAME = "ReviewSaaS"
    FORCE_HTTPS = bool(int(os.getenv("FORCE_HTTPS", "0")))
    CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")
settings = Settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    try:
        init_db(drop_existing=os.getenv("DROP_ALL_TABLES") == "1")
        logger.info("Database sync complete.")
    except Exception as e:
        logger.error(f"DB init error: {e}")
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "supersecretkey123"),
)
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        if settings.FORCE_HTTPS and scheme != "https":
            return RedirectResponse(request.url.replace(scheme="https"), status_code=307)
        return await call_next(request)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ALLOW_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Templates & Static
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ----- Jinja Globals -----
def jinja_now():
    return datetime.now(timezone.utc)

def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    # Return hidden input that templates can include directly
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')

templates.env.globals["now"] = jinja_now
templates.env.globals["csrf_token"] = ensure_csrf  # used as csrf_token() in templates

# ----- Common Context -----
def common_context(request: Request) -> Dict[str, Any]:
    try:
        user = get_current_user(request)
    except Exception:
        user = None

    db = next(get_db())
    try:
        companies_list = db.query(Company).order_by(Company.name.asc()).all()
    except Exception:
        companies_list = []
    finally:
        db.close()

    return {
        "request": request,
        "current_user": user,
        "is_authenticated": user is not None,
        "companies": companies_list,
    }

# WebSocket
@app.websocket("/ws/dashboard")
asyncAwesome — I’ll update the **existing files only** (no new files), so your **frontend templates keep interacting with the same paths**. Below are **complete, drop-in replacements** for each file you asked to update.

> ✅ What this gives you:
> - `/dashboard` now **populates every variable** your `dashboard.html` expects.
> - `/companies/create`, `/companies/{id}/delete`, `/sync/run?company_id=` **match the template**.
> - `/reviews/{id}/reply/suggest` and `/reviews/{id}/reply` **work from the table form**.
> - `/reports?company_id=&format=` (csv/xlsx/pdf) **exports correctly**.
> - RBAC exposes `is_authenticated` + `roles` for the navbar/hero.
> - Jinja globals: `now()` and `csrf_token()`, + `common_context` unchanged.
> - Reviews API aligned to `{ total, page, limit, data }`.
> - Metrics/AI services return **the exact shapes** your charts and summary need.
> - `/logout` route exists.

---

## 1) `app/routes/dashboard.py` — **Populate all context expected by `dashboard.html`**

```python
# FILE: app/routes/dashboard.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app import models
from app.services import metrics as metrics_svc
from app.services import ai_insights as ai_svc
from app.services.rbac import get_current_user, get_user_roles_for_company

# Jinja
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _apply_quick_range(range_key: Optional[str]) -> (Optional[datetime], Optional[datetime]):
    if not range_key:
        return None, None
    now = datetime.now(timezone.utc)
    if range_key == "7d":
        return now - timedelta(days=7), now
    if range_key == "30d":
        return now - timedelta(days=30), now
    if range_key == "90d":
        return now - timedelta(days=90), now
    if range_key == "qtr":
        # This quarter
        q = (now.month - 1) // 3 + 1
        start_month = 3 * (q - 1) + 1
        start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    return None, None

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    company_id: Optional[int] = Query(None),
    range: Optional[str] = Query(None, pattern="^(7d|30d|90d|qtr)$"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Companies visible to the user
    if getattr(current_user, "role", None) == "admin":
        companies = db.query(models.Company).order_by(models.Company.created_at.desc()).all()
    else:
        companies = (
            db.query(models.Company)
            .filter(models.Company.owner_id == current_user.id)
            .order_by(models.Company.created_at.desc())
            .all()
        )

    if not companies:
        # Render page with empty state
        context = {
            "request": request,
            "companies": [],
            "active_company": None,
            "params": {"from": from_ or "", "to": to or "", "range": range or ""},
            "kpi": {},
            "charts": {"labels": [], "sentiment": [], "rating": [], "dist": {"1":0,"2":0,"3":0,"4":0,"5":0}, "correlation": [], "benchmark": {"labels":[],"series":[]}},
            "reviews": [],
            "summary": "No companies yet. Add one to get started.",
            "api_health": [],
            "roles": [],
            "alerts": [],
        }
        return templates.TemplateResponse("dashboard.html", context)

    # Select active company (query param or first available)
    active_company = None
    if company_id:
        active_company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not active_company:
        active_company = companies[0]
        company_id = active_company.id

    # Dates: quick range or explicit from/to
    sdt, edt = _apply_quick_range(range)
    if from_:
        sdt = _parse_date(from_)
    if to:
        edt = _parse_date(to)
    # Normalize dates for SQL filtering
    if sdt and not sdt.tzinfo:
        sdt = sdt.replace(tzinfo=timezone.utc)
    if edt and not edt.tzinfo:
        edt = edt.replace(tzinfo=timezone.utc)

    # Pull reviews in window
    q = db.query(models.Review).filter(models.Review.company_id == company_id)
    if sdt:
        q = q.filter(models.Review.review_date >= sdt)
    if edt:
        q = q.filter(models.Review.review_date <= edt)
    reviews: List[models.Review] = q.order_by(models.Review.review_date.desc()).all()

    # KPI snapshot
    kpi = metrics_svc.build_kpi_for_dashboard(db, company_id, sdt, edt)

    # Charts (exact shapes required by dashboard.html)
    charts = metrics_svc.build_dashboard_charts(db, company_id, sdt, edt)

    # Executive summary (AI)
    ai_report = ai_svc.analyze_reviews(reviews, active_company, sdt, edt) or {}
    summary_text = ai_report.get("summary_text") or ai_report.get("executive_text") or "No summary available yet."

    # API health snapshot (list of {provider, status})
    health_rows = db.query(models.ApiHealthCheck).filter(models.ApiHealthCheck.company_id == company_id).order_by(models.ApiHealthCheck.checked_at.desc()).all()
    api_health = [{"provider": h.provider, "status": h.status} for h in health_rows] if health_rows else []

    # Alerts (list of recent)
    alerts = (
        db.query(models.Alert)
        .filter(models.Alert.company_id == company_id)
        .order_by(models.Alert.occurred_at.desc())
        .limit(10)
        .all()
    )

    # Role badges for conditional sections
    roles = get_user_roles_for_company(db, current_user, company_id)

    # Build review view model (attach suggested/user reply for the table UI)
    # Fetch all replies per review id
    replies_by_review: Dict[int, models.Reply] = {}
    reply_rows = (
        db.query(models.Reply)
        .join(models.Review, models.Reply.review_id == models.Review.id)
        .filter(models.Review.company_id == company_id)
        .all()
    )
    for rp in reply_rows:
        # keep latest by suggested/sent timestamps
        if rp.review_id not in replies_by_review:
            replies_by_review[rp.review_id] = rp
        else:
            old = replies_by_review[rp.review_id]
            if (rp.sent_at or rp.suggested_at) and (old.sent_at or old.suggested_at):
                if (rp.sent_at or rp.suggested_at) > (old.sent_at or old.suggested_at):
                    replies_by_review[rp.review_id] = rp

    review_vm = []
    for r in reviews:
        latest_reply = replies_by_review.get(r.id)
        vm = SimpleNamespace(
            id=r.id,
            review_date=r.review_date,
            reviewer_name=r.reviewer_name,
            rating=r.rating,
            sentiment_category=r.sentiment_category,
            sentiment_score=r.sentiment_score,
            sentiment_confidence=r.sentiment_confidence,
            emotion_label=r.emotion_label,
            is_spam_suspected=r.is_spam_suspected,
            aspect_summary=r.aspect_summary,
            topics=r.topics,
            keywords=r.keywords,
            language=r.language,
            text=r.text,
            ai_suggested_reply=(latest_reply.suggested_text if latest_reply else None),
            user_reply=(latest_reply.edited_text if latest_reply and latest_reply.status in ("Sent", "Posted") else None),
        )
        review_vm.append(vm)

    context = {
        "request": request,
        "companies": companies,
        "active_company": active_company,
        "params": {"from": from_ or "", "to": to or "", "range": range or ""},
        "kpi": kpi,
        "charts": charts,
        "reviews": review_vm,
        "summary": summary_text,
        "api_health": api_health,
        "roles": roles,
        "alerts": alerts,
    }
    return templates.TemplateResponse("dashboard.html", context)
