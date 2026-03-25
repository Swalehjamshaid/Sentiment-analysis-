# =============================================
# Final Working Dockerfile for Railway 
# (Playwright + FastAPI + Gunicorn + $PORT fix)
# =============================================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# 1. Copy and install dependencies first (this layer is cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Download Firefox browser (needed for your scraper)
RUN playwright install firefox --with-deps

# 3. Copy your application code (this layer rebuilds when you change scraper.py)
COPY . .

# 4. Expose port (for documentation)
EXPOSE 8080

# 5. FIXED START COMMAND FOR RAILWAY
# This uses shell form so $PORT variable from Railway gets properly expanded
CMD ["sh", "-c", "gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8080}"]
