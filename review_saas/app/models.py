# FILE: app/models.py
# Purpose: SQLAlchemy models updated to fulfill the 31-point requirements for the
# review analytics platform. This file preserves the original schema and extends it
# with additional tables, fields, constraints, and indexes to support multi-source
# integrations, sync & API health, advanced NLP analytics (sentiment, emotion,
# aspect-based scores, keyword extraction), RBAC, alerts, forecasting, reporting,
# benchmarking, and compliance-friendly auditing.
#
# NOTE FOR MAINTAINERS:
# - This module defines DB structures only. Business logic (AI/ML, Google API
#   service connectors, async jobs) should live in the service layer.
# - Keep migrations in sync (e.g., Alembic). New or changed enums/columns require
#   explicit migration scripts.

from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Float,
    UniqueConstraint,
    Index,
    Enum,
    JSON,
)
from datetime import datetime, timezone

Base = declarative_base()

# =========================================================
# USER MODEL
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    profile_pic_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # === Relationships ===
    companies = relationship("Company", back_populates="owner", cascade="all, delete-orphan")
    verification_tokens = relationship("VerificationToken", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("ResetToken", back_populates="user", cascade="all, delete-orphan")
    login_attempts = relationship("LoginAttempt", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    roles = relationship("UserCompanyRole", back_populates="user", cascade="all, delete-orphan")
    dashboard_configs = relationship("DashboardConfig", back_populates="user", cascade="all, delete-orphan")
    api_credentials = relationship("ApiCredential", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


# =========================================================
# TOKEN & LOG MODELS
# =========================================================

class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="verification_tokens")


class ResetToken(Base):
    __tablename__ = "reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="reset_tokens")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    success = Column(Boolean, nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="login_attempts")


# =========================================================
# COMPANY MODEL (supports multi-branch + benchmarking)
# =========================================================

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    place_id = Column(String(128), nullable=True)  # Google place identifier
    maps_link = Column(String(512), nullable=True)

    city = Column(String(128), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    logo_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # CRITICAL: Field to track last sync with Google API
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)  # success, partial, failed
    last_sync_message = Column(String(512), nullable=True)

    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)

    # Branching / hierarchy for multi-location businesses
    parent_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    # === Relationships ===
    owner = relationship("User", back_populates="companies")
    parent = relationship("Company", remote_side=[id], backref="branches")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="company", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    roles = relationship("UserCompanyRole", back_populates="company", cascade="all, delete-orphan")
    sync_jobs = relationship("SyncJob", back_populates="company", cascade="all, delete-orphan")
    competitors = relationship("CompetitorLink", back_populates="company", cascade="all, delete-orphan")
    metrics_daily = relationship("CompanyDailyMetrics", back_populates="company", cascade="all, delete-orphan")
    forecasts = relationship("CompanyForecast", back_populates="company", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_company_owner_status", "owner_id", "status"),
        Index("idx_company_place_id", "place_id"),
        Index("idx_company_created", "created_at"),
        Index("idx_company_parent", "parent_id"),
        Index("idx_company_city", "city"),
    )


# =========================================================
# REVIEW SOURCE (multi-source: Google, Facebook, X, AppStore, Survey, etc.)
# =========================================================

class ReviewSource(Base):
    __tablename__ = "review_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)  # e.g., GOOGLE, FACEBOOK, X, APP_STORE, SURVEY
    provider = Column(String(64), nullable=False)  # e.g., google, meta, apple
    description = Column(String(255), nullable=True)
    base_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uq_source_name"),)


# =========================================================
# REVIEW MODEL (advanced NLP: sentiment, emotion, aspects, keywords)
# =========================================================

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Multi-source linkage
    source_id = Column(Integer, ForeignKey("review_sources.id", ondelete="SET NULL"), nullable=True)

    external_id = Column(String(128), nullable=True)  # provider-specific review id
    text = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5

    # CRITICAL: Must be DateTime to support hour extraction in analytics
    review_date = Column(DateTime, nullable=True)
    reviewer_name = Column(String(255), nullable=True)
    reviewer_avatar = Column(String(255), nullable=True)

    # Sentiment (3. Advanced Sentiment Classification)
    sentiment_category = Column(String(20), nullable=True)  # Positive, Negative, Neutral
    sentiment_score = Column(Float, nullable=True)  # normalized -1..1 or 0..1 depending on model
    sentiment_confidence = Column(Float, nullable=True)

    # Emotion detection (4. Emotion Detection Layer)
    emotion_label = Column(String(32), nullable=True)  # e.g., satisfaction, anger
    emotion_scores = Column(JSON, nullable=True)  # {"joy": 0.82, "anger": 0.05, ...}

    # Aspect-based sentiment (5. Aspect-Based)
    # Stored in child table ReviewAspect; summary JSON for quick reads
    aspect_summary = Column(JSON, nullable=True)  # {"service": {"score":0.8}, ...}

    # Keywords & topics (6. Keyword & Topic Extraction)
    # Stored in child table ReviewKeyword; summary JSON for quick reads
    keywords = Column(String(512), nullable=True)  # backward-compat simple CSV
    topics = Column(JSON, nullable=True)  # {"delivery": 0.62, "price": 0.41}

    # Multi-language (24. Multi-Language Support)
    language = Column(String(10), nullable=True)
    language_confidence = Column(Float, nullable=True)
    translated_text = Column(Text, nullable=True)  # if auto-translated for analysis

    # Customer journey stage (25. Customer Journey Insights)
    journey_stage = Column(String(32), nullable=True)  # pre_purchase|purchase|post_purchase

    # Fetch & integrity
    fetch_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    fetch_status = Column(String(20), default="Success", nullable=False)

    # Anomaly & spam flags (27. Anomaly Detection)
    is_spam_suspected = Column(Boolean, default=False, nullable=False)
    anomaly_score = Column(Float, nullable=True)  # outlier likelihood 0..1

    company = relationship("Company", back_populates="reviews")
    replies = relationship("Reply", back_populates="review", cascade="all, delete-orphan")
    source = relationship("ReviewSource")
    aspects = relationship("ReviewAspect", back_populates="review", cascade="all, delete-orphan")
    keyword_links = relationship("ReviewKeyword", back_populates="review", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "external_id", name="uq_review_company_ext"),
        Index("idx_review_company_date", "company_id", "review_date"),
        Index("idx_review_rating", "rating"),
        Index("idx_review_sentiment", "sentiment_category"),
        Index("idx_review_language", "language"),
        Index("idx_review_source", "source_id"),
        Index("idx_review_anomaly", "is_spam_suspected", "anomaly_score"),
    )


# =========================================================
# SUPPORTING MODELS (aspects, keywords, replies, reports)
# =========================================================

class ReviewAspect(Base):
    __tablename__ = "review_aspects"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    aspect = Column(String(64), nullable=False)  # e.g., service, price, quality, staff, delivery
    sentiment_score = Column(Float, nullable=True)
    sentiment_category = Column(String(20), nullable=True)

    review = relationship("Review", back_populates="aspects")

    __table_args__ = (
        Index("idx_aspect_review", "review_id"),
        Index("idx_aspect_name", "aspect"),
    )


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    term = Column(String(128), nullable=False)
    language = Column(String(10), nullable=True)

    __table_args__ = (UniqueConstraint("term", "language", name="uq_keyword_term_lang"),)


class ReviewKeyword(Base):
    __tablename__ = "review_keywords"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    weight = Column(Float, nullable=True)  # importance/TF-IDF score

    review = relationship("Review", back_populates="keyword_links")
    keyword = relationship("Keyword")

    __table_args__ = (
        UniqueConstraint("review_id", "keyword_id", name="uq_review_keyword"),
        Index("idx_review_keyword_review", "review_id"),
        Index("idx_review_keyword_keyword", "keyword_id"),
    )


class Reply(Base):
    __tablename__ = "replies"

    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)

    suggested_text = Column(Text, nullable=True)
    edited_text = Column(Text, nullable=True)

    status = Column(String(20), default="Draft", nullable=False)  # Draft, Sent, Posted, Failed
    suggested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at = Column(DateTime, nullable=True)

    # Engagement & response tracking (26.)
    responder_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=True, nullable=False)

    review = relationship("Review", back_populates="replies")
    responder = relationship("User")

    __table_args__ = (
        Index("idx_reply_review", "review_id"),
        Index("idx_reply_status", "status"),
    )


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(255), nullable=True)
    path = Column(String(512), nullable=True)
    meta = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Extended for export formats & periods (19., 20.)
    format = Column(String(16), nullable=True)  # pdf, xlsx, csv
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)

    company = relationship("Company", back_populates="reports")

    __table_args__ = (
        Index("idx_report_company_date", "company_id", "generated_at"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)

    kind = Column(String(50), nullable=True)
    payload = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    read = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="notifications")
    company = relationship("Company", back_populates="notifications")

    __table_args__ = (
        Index("idx_notification_user_read", "user_id", "read"),
        Index("idx_notification_company", "company_id"),
    )


# =========================================================
# RBAC (22. Role-Based Access Control)
# =========================================================

class UserCompanyRole(Base):
    __tablename__ = "user_company_roles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)  # owner, manager, analyst, viewer

    user = relationship("User", back_populates="roles")
    company = relationship("Company", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_company_role"),
        Index("idx_user_company", "user_id", "company_id"),
        Index("idx_role", "role"),
    )


# =========================================================
# API CREDENTIALS, HEALTH & SYNC (1., 2., 23., 31.)
# =========================================================

class ApiCredential(Base):
    __tablename__ = "api_credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    provider = Column(String(64), nullable=False)  # google, meta, apple, custom
    account_label = Column(String(128), nullable=True)

    # OAuth tokens (should be encrypted at rest by the app layer/KMS)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    scopes = Column(Text, nullable=True)  # space- or comma-separated

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="api_credentials")
    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint("company_id", "provider", name="uq_company_provider_cred"),
        Index("idx_cred_provider", "provider"),
    )


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)

    endpoint = Column(String(255), nullable=True)
    method = Column(String(16), nullable=True)
    status_code = Column(Integer, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(String(512), nullable=True)

    request_id = Column(String(128), nullable=True)
    rate_limit_remaining = Column(Integer, nullable=True)
    rate_limit_reset_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_api_log_company_time", "company_id", "created_at"),
        Index("idx_api_log_provider_status", "provider", "status_code"),
    )


class ApiHealthCheck(Base):
    __tablename__ = "api_health_checks"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)  # healthy|degraded|down
    details = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_api_health_company_provider", "company_id", "provider"),
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)  # e.g., google

    schedule = Column(String(64), nullable=True)  # cron or preset (realtime, 15min, hourly)
    enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="sync_jobs")
    runs = relationship("SyncRun", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "provider", name="uq_sync_company_provider"),
        Index("idx_sync_company_provider", "company_id", "provider"),
    )


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False)

    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False, default="running")  # running|success|partial|failed
    summary = Column(Text, nullable=True)

    job = relationship("SyncJob", back_populates="runs")

    __table_args__ = (
        Index("idx_syncrun_job", "job_id"),
        Index("idx_syncrun_status", "status"),
    )


# =========================================================
# METRICS, BENCHMARKING & FORECASTS (7., 9., 11., 12., 13., 20., 21., 26.)
# =========================================================

class CompanyDailyMetrics(Base):
    __tablename__ = "company_daily_metrics"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)

    # Volume & ratings
    review_count = Column(Integer, default=0, nullable=False)
    avg_rating = Column(Float, nullable=True)

    # Sentiment
    avg_sentiment = Column(Float, nullable=True)
    pos_count = Column(Integer, default=0, nullable=False)
    neu_count = Column(Integer, default=0, nullable=False)
    neg_count = Column(Integer, default=0, nullable=False)

    # Response time (seconds) and engagement
    avg_response_time_s = Column(Float, nullable=True)
    response_rate = Column(Float, nullable=True)  # 0..1

    # Cached distributions for quick charts
    rating_distribution = Column(JSON, nullable=True)  # {"1": 3, "2": 1, ...}
    sentiment_distribution = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", back_populates="metrics_daily")

    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_company_day"),
        Index("idx_metrics_company_date", "company_id", "date"),
    )


class CompetitorLink(Base):
    __tablename__ = "competitor_links"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Competitor can be internal (another Company row) or external by provider/place_id
    competitor_company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String(64), nullable=True)
    external_place_id = Column(String(128), nullable=True)
    label = Column(String(128), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", foreign_keys=[company_id], back_populates="competitors")
    competitor_company = relationship("Company", foreign_keys=[competitor_company_id])

    __table_args__ = (
        Index("idx_competitor_company", "company_id"),
    )


class CompanyForecast(Base):
    __tablename__ = "company_forecasts"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    target = Column(String(64), nullable=False)  # avg_rating, review_count, avg_sentiment
    forecast_date = Column(DateTime, nullable=False)
    forecast_value = Column(Float, nullable=False)
    model_name = Column(String(128), nullable=True)
    horizon = Column(Integer, nullable=True)  # days ahead
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", back_populates="forecasts")

    __table_args__ = (
        Index("idx_forecast_company_target_date", "company_id", "target", "forecast_date"),
    )


# =========================================================
# ALERTING (15.) with rules and events
# =========================================================

class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(128), nullable=False)
    kind = Column(String(64), nullable=False)  # negative_spike, rating_drop, anomaly_surge
    threshold = Column(Float, nullable=True)
    window = Column(String(32), nullable=True)  # e.g., 1d, 7d
    enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_alertrule_company", "company_id"),
        Index("idx_alertrule_kind", "kind"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(Integer, ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True)

    severity = Column(String(16), nullable=False, default="info")  # info|warning|critical
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    acknowledged = Column(Boolean, default=False, nullable=False)

    company = relationship("Company", back_populates="alerts")

    __table_args__ = (
        Index("idx_alert_company_time", "company_id", "occurred_at"),
        Index("idx_alert_ack", "acknowledged"),
    )


# =========================================================
# DASHBOARD CONFIG (17. Customizable KPI Dashboard)
# =========================================================

class DashboardConfig(Base):
    __tablename__ = "dashboard_configs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # JSON config with widgets, KPI selection, date ranges, chart preferences
    config = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="dashboard_configs")

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_dashboard_user_company"),
        Index("idx_dash_user_company", "user_id", "company_id"),
    )


# =========================================================
# ANOMALY EVENTS (27.) & AUDIT (29.)
# =========================================================

class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True)

    kind = Column(String(64), nullable=False)  # spam_pattern, sudden_drop, volume_spike
    score = Column(Float, nullable=False)
    details = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_anomaly_company_time", "company_id", "detected_at"),
        Index("idx_anomaly_kind", "kind"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    action = Column(String(64), nullable=False)  # login, export_pdf, change_role, api_sync
    entity = Column(String(64), nullable=True)  # Review, Company, Reply, Report
    entity_id = Column(String(64), nullable=True)
    changes = Column(JSON, nullable=True)  # diff/summary
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_company_time", "company_id", "created_at"),
        Index("idx_audit_action", "action"),
    )
