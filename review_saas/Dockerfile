# =============================================
# Final Railway Dockerfile - Playwright + FastAPI (Fixed)
# =============================================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# Install Python dependencies first (cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Firefox browser (critical for your scraper)
RUN playwright install firefox --with-deps

# Copy your code last
COPY . .

EXPOSE 8080

# Correct shell form for Railway $PORT
CMD sh -c "gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:\${PORT:-8080}"
