# FILE: app/models.py
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, Text,
    ForeignKey, JSON, UniqueConstraint, Index
)
from datetime import datetime, timezone

Base = declarative_base()

def now_utc():
    return datetime.now(timezone.utc)

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
    created_at = Column(DateTime, default=now_utc, nullable=False)

    # Relationships
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
# TOKEN MODELS
# =========================================================

class VerificationToken(Base):
    __tablename__ = "verification_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="verification_tokens")

class ResetToken(Base):
    __tablename__ = "reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="reset_tokens")

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    success = Column(Boolean, nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="login_attempts")

# =========================================================
# COMPANY MODEL
# =========================================================

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    # Ensure owner_id is explicitly Integer to match User.id
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    place_id = Column(String(128), nullable=True)
    maps_link = Column(String(512), nullable=True)
    city = Column(String(128), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    logo_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    last_sync_message = Column(String(512), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    owner = relationship("User", back_populates="companies")
    parent = relationship("Company", remote_side=[id], backref="branches")
    reviews = relationship("Review", back_populates="company", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="company", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    roles = relationship("UserCompanyRole", back_populates="company", cascade="all, delete-orphan")
    sync_jobs = relationship("SyncJob", back_populates="company", cascade="all, delete-orphan")
    
    # Resolves multiple FK ambiguity for competitors
    competitors = relationship(
        "CompetitorLink", 
        foreign_keys="[CompetitorLink.company_id]", 
        back_populates="company", 
        cascade="all, delete-orphan"
    )
    
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
# REVIEW SOURCE MODEL
# =========================================================

class ReviewSource(Base):
    __tablename__ = "review_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    description = Column(String(255), nullable=True)
    base_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint("name", name="uq_source_name"),)

# =========================================================
# REVIEW MODEL
# =========================================================

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(Integer, ForeignKey("review_sources.id", ondelete="SET NULL"), nullable=True)
    external_id = Column(String(128), nullable=True)
    text = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    review_date = Column(DateTime, nullable=True)
    reviewer_name = Column(String(255), nullable=True)
    reviewer_avatar = Column(String(255), nullable=True)

    sentiment_category = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    sentiment_confidence = Column(Float, nullable=True)
    emotion_label = Column(String(32), nullable=True)
    emotion_scores = Column(JSON, nullable=True)
    aspect_summary = Column(JSON, nullable=True)
    keywords = Column(String(512), nullable=True)
    topics = Column(JSON, nullable=True)
    language = Column(String(10), nullable=True)
    language_confidence = Column(Float, nullable=True)
    translated_text = Column(Text, nullable=True)
    journey_stage = Column(String(32), nullable=True)

    fetch_at = Column(DateTime, default=now_utc, nullable=False)
    fetch_status = Column(String(20), default="Success", nullable=False)
    is_spam_suspected = Column(Boolean, default=False, nullable=False)
    anomaly_score = Column(Float, nullable=True)

    company = relationship("Company", back_populates="reviews")
    source = relationship("ReviewSource")
    replies = relationship("Reply", back_populates="review", cascade="all, delete-orphan")
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
# REPLY MODEL
# =========================================================

class Reply(Base):
    __tablename__ = "replies"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    replied_at = Column(DateTime, default=now_utc, nullable=False)
    responder_name = Column(String(255), nullable=True)
    responder_role = Column(String(64), nullable=True)
    review = relationship("Review", back_populates="replies")

# =========================================================
# REVIEW ASPECT & KEYWORD MODELS
# =========================================================

class ReviewAspect(Base):
    __tablename__ = "review_aspects"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    aspect = Column(String(128), nullable=False)
    sentiment = Column(String(20), nullable=True)
    score = Column(Float, nullable=True)
    review = relationship("Review", back_populates="aspects")

class ReviewKeyword(Base):
    __tablename__ = "review_keywords"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(128), nullable=False)
    relevance = Column(Float, nullable=True)
    review = relationship("Review", back_populates="keyword_links")

# =========================================================
# REPORT MODEL
# =========================================================

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    company = relationship("Company", back_populates="reports")

# =========================================================
# NOTIFICATION MODEL
# =========================================================

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    type = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="notifications")
    company = relationship("Company", back_populates="notifications")

# =========================================================
# USER-COMPANY ROLE MODEL (RBAC)
# =========================================================

class UserCompanyRole(Base):
    __tablename__ = "user_company_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)
    assigned_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="roles")
    company = relationship("Company", back_populates="roles")
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_user_company_role"),)

# =========================================================
# API CREDENTIAL & LOGGING MODELS
# =========================================================

class ApiCredential(Base):
    __tablename__ = "api_credentials"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)
    api_key = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="api_credentials")

class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    provider = Column(String(64), nullable=False)
    endpoint = Column(String(255), nullable=False)
    request_payload = Column(JSON, nullable=True)
    response_status = Column(Integer, nullable=False)
    response_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)

class ApiHealthCheck(Base):
    __tablename__ = "api_health_checks"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    provider = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    last_checked_at = Column(DateTime, default=now_utc, nullable=False)
    details = Column(JSON, nullable=True)

# =========================================================
# SYNC MODELS
# =========================================================

class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    company = relationship("Company", back_populates="sync_jobs")
    runs = relationship("SyncRun", back_populates="job", cascade="all, delete-orphan")

class SyncRun(Base):
    __tablename__ = "sync_runs"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=now_utc, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    fetched_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    job = relationship("SyncJob", back_populates="runs")

# =========================================================
# COMPANY METRICS & FORECAST MODELS
# =========================================================

class CompanyDailyMetrics(Base):
    __tablename__ = "company_daily_metrics"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)
    total_reviews = Column(Integer, nullable=True)
    avg_rating = Column(Float, nullable=True)
    sentiment_positive = Column(Float, nullable=True)
    sentiment_negative = Column(Float, nullable=True)
    sentiment_neutral = Column(Float, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    company = relationship("Company", back_populates="metrics_daily")
    __table_args__ = (UniqueConstraint("company_id", "date", name="uq_company_date_metrics"),)

class CompanyForecast(Base):
    __tablename__ = "company_forecasts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    metric = Column(String(64), nullable=False)
    forecast_value = Column(Float, nullable=False)
    forecast_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    company = relationship("Company", back_populates="forecasts")
    __table_args__ = (UniqueConstraint("company_id", "metric", "forecast_date", name="uq_company_metric_forecast"),)

# =========================================================
# COMPETITOR MODEL
# =========================================================

class CompetitorLink(Base):
    __tablename__ = "competitor_links"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    competitor_company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)

    company = relationship("Company", foreign_keys=[company_id], back_populates="competitors")
    competitor = relationship("Company", foreign_keys=[competitor_company_id])

# =========================================================
# ALERT MODELS
# =========================================================

class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    metric = Column(String(64), nullable=False)
    condition = Column(String(64), nullable=False)
    threshold = Column(Float, nullable=False)
    created_at = Column(DateTime, default=now_utc, nullable=False)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    triggered_at = Column(DateTime, default=now_utc, nullable=False)
    value = Column(Float, nullable=True)
    status = Column(String(32), nullable=False, default="unread")
    company = relationship("Company", back_populates="alerts")
    rule = relationship("AlertRule")

# =========================================================
# DASHBOARD CONFIGS
# =========================================================

class DashboardConfig(Base):
    __tablename__ = "dashboard_configs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    widget_type = Column(String(64), nullable=False)
    settings = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, nullable=False, onupdate=now_utc)
    user = relationship("User", back_populates="dashboard_configs")
    company = relationship("Company")

# =========================================================
# AUDIT LOGS
# =========================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=now_utc, nullable=False)
    user = relationship("User", back_populates="audit_logs")

# =========================================================
# ANOMALY EVENT MODEL
# =========================================================

class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    id = Column(Integer, primary_key=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    score = Column(Float, nullable=False)
    detected_at = Column(DateTime, default=now_utc, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)
    review = relationship("Review")
    company = relationship("Company")
