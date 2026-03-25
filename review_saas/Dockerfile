# ================================
# BASE IMAGE
# ================================
FROM python:3.11-slim

# ================================
# ENVIRONMENT CONFIG
# ================================
ENV PYTHONUNBUFFERED=1 \
    # Sync Playwright path for the scraper
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MALLOC_ARENA_MAX=2

# ================================
# SYSTEM DEPENDENCIES
# ================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxcomposite1 libxdamage1 libxrandr2 libx11-xcb1 \
    libxss1 libxshmfence1 libglib2.0-0 libgtk-3-0 \
    libdbus-glib-1-2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ================================
# WORKDIR & PYTHON INSTALL
# ================================
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ================================
# BROWSER INSTALLATION (CRITICAL)
# ================================
# This ensures the browser exists before the backend tries to call it
RUN playwright install --with-deps chromium

# ================================
# APPLICATION CODE
# ================================
COPY . .

# ================================
# START SERVER (BACKEND SYNC)
# ================================
EXPOSE 8080
# Timeout 120 ensures the scraper has time to finish before Gunicorn kills it
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120"]
