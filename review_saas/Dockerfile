# ============================================
#  Playwright + FastAPI Production Dockerfile
# ============================================

FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Install dependencies
# NOTE: setuptools==68.2.2 is REQUIRED for Python 3.12 compatibility with stealth-who
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy application code
COPY . /app/

# Use non-root user
RUN useradd -m appuser
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8080

# Start FastAPI via Gunicorn + Uvicorn workers
CMD ["gunicorn", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120", "--bind", "0.0.0.0:8080", "app.main:app"]
