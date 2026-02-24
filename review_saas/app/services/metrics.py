# app/services/metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time
import threading

# -------------------------------
# Prometheus Metrics Definitions
# -------------------------------

REQUESTS_TOTAL = Counter(
    "api_requests_total",
    "Total API requests",
    labelnames=("route", "method", "status_family", "plan_tier"),
)

REQUEST_LATENCY_SECONDS = Histogram(
    "api_request_latency_seconds",
    "Request latency (s)",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    labelnames=("route", "method", "plan_tier"),
)

INFLIGHT_REQUESTS = Gauge(
    "api_inflight_requests",
    "In-flight requests",
    labelnames=("route", "plan_tier"),
)

# -------------------------------
# Utility Functions
# -------------------------------

def _status_family(status_code: int) -> str:
    return f"{status_code//100}xx"

def sanitize_label(value: str, max_len: int = 64) -> str:
    if value is None:
        return "unknown"
    v = value.strip().lower()
    return v[:max_len]

# -------------------------------
# Metrics Wrapper Class
# -------------------------------

class Metrics:
    """Thin wrapper to centralize label rules and avoid direct client use across codebase."""

    def record_request(self, route: str, method: str, status_code: int, plan_tier: str, duration_s: float):
        route = sanitize_label(route)
        method = sanitize_label(method)
        tier = sanitize_label(plan_tier)
        REQUESTS_TOTAL.labels(route, method, _status_family(status_code), tier).inc()
        REQUEST_LATENCY_SECONDS.labels(route, method, tier).observe(duration_s)

    def track_inflight(self, route: str, plan_tier: str):
        route = sanitize_label(route)
        tier = sanitize_label(plan_tier)
        gauge = INFLIGHT_REQUESTS.labels(route, tier)
        gauge.inc()
        try:
            yield
        finally:
            gauge.dec()

metrics = Metrics()

# -------------------------------
# Stub Functions for Imports
# -------------------------------

def aggregate_trends(metric_name: str, labels: dict = None):
    """
    Aggregate trends stub.
    Replace with actual logic to compute trends if needed.
    """
    labels = labels or {}
    # Example: return empty list or dummy trend data
    return {"metric": metric_name, "labels": labels, "values": []}

def aggregate_rating_distribution(metric_name: str, labels: dict = None):
    """
    Aggregate rating distribution stub.
    Replace with actual logic to compute rating distributions.
    """
    labels = labels or {}
    # Example: return dummy rating distribution
    return {"metric": metric_name, "labels": labels, "distribution": {}}
