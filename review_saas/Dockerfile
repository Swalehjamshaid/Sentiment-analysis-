# =============================================
# Railway-Optimized Dockerfile for Playwright Scraper (Fixed)
# =============================================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# 1. Install Python dependencies first (this layer caches well)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Install Firefox browser + dependencies with retry + timeout handling
RUN playwright install firefox --with-deps || \
    (echo "Retrying browser install..." && sleep 10 && playwright install firefox --with-deps)

# 3. Copy your code last (fast rebuilds for scraper.py changes)
COPY . .

EXPOSE 8080

# Fixed start command for Railway ($PORT expansion)
CMD sh -c "gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:\${PORT:-8080}"
