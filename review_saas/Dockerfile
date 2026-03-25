# ================================
# BASE IMAGE
# ================================
FROM python:3.11-slim

# ================================
# ENVIRONMENT VARIABLES
# ================================
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    # Ensuring Playwright knows where the browsers are in Linux
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    # Crucial for Railway memory management
    MALLOC_ARENA_MAX=2

# ================================
# SYSTEM DEPENDENCIES (Full Playwright Support)
# ================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    # These are the specific Linux libs needed for Headless Firefox/Chromium
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libx11-xcb1 \
    libxss1 \
    libxshmfence1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ================================
# WORKDIR & COPY
# ================================
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# ================================
# INSTALL BROWSERS (Aligned with Scraper)
# ================================
# We install both Chromium and Firefox to match the Video + Railway logic
# using 'playwright' or 'patchright' (they share the same install CLI)
RUN playwright install --with-deps chromium firefox

# ================================
# DEPLOYMENT SETTINGS
# ================================
EXPOSE 8080

# Start command with the 120s timeout to prevent mid-scrape crashes
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120"]
