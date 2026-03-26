# ============================================
#  Playwright + FastAPI Production Dockerfile
# ============================================

FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy application source code
COPY . /app/

# Run as non-root user
RUN useradd -m appuser
USER appuser

# Expose port (Cloud Run ignores this, but we keep it for local use)
EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ==============================
# ⭐ CRITICAL FIX (Cloud Run PORT)
# ==============================
# Cloud Run passes a dynamic port via $PORT.
# Shell ("sh -c") is required so ${PORT} expands.
CMD ["sh", "-c", "gunicorn --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 120 --bind 0.0.0.0:${PORT} app.main:app"]
