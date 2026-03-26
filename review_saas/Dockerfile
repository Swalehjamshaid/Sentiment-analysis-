# ============================================
#  Playwright + FastAPI Production Dockerfile
# ============================================

FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt /app/

# Install Python dependencies
# IMPORTANT: Install setuptools AFTER requirements to restore pkg_resources
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy application code
COPY . /app/

# Create non-root user
RUN useradd -m appuser
USER appuser

# Expose API port
EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8080

# Start FastAPI with Gunicorn + Uvicorn worker
CMD ["gunicorn", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120", "--bind", "0.0.0.0:8080", "app.main:app"]
