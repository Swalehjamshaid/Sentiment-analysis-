# ==========================================================
# TRUSTLYTICS AI — FINAL STABLE RAILWAY DOCKERFILE
# MAY 2026 ENTERPRISE PRODUCTION VERSION
#
# FEATURES:
# ✅ FastAPI
# ✅ Playwright
# ✅ Google Maps Scraping
# ✅ AI Chatbot
# ✅ PDF Reporting
# ✅ Railway Stable
# ✅ Lightweight
# ✅ No Chromium Conflicts
# ✅ No OS Compatibility Warning
# ✅ Production Optimized
# ==========================================================

# ==========================================================
# USE OFFICIAL PLAYWRIGHT IMAGE
# ==========================================================

FROM mcr.microsoft.com/playwright/python:v1.53.0-jammy

# ==========================================================
# ENVIRONMENT VARIABLES
# ==========================================================

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ==========================================================
# WORK DIRECTORY
# ==========================================================

WORKDIR /app

# ==========================================================
# INSTALL REQUIRED SYSTEM PACKAGES ONLY
# ==========================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    wget \
    git \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ==========================================================
# COPY REQUIREMENTS
# ==========================================================

COPY requirements.txt .

# ==========================================================
# UPGRADE PIP
# ==========================================================

RUN python -m pip install --upgrade \
    pip \
    setuptools \
    wheel

# ==========================================================
# INSTALL PYTHON DEPENDENCIES
# ==========================================================

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================================
# CREATE REQUIRED DIRECTORIES
# ==========================================================

RUN mkdir -p \
    /tmp \
    /app/logs \
    /app/uploads

# ==========================================================
# COPY APPLICATION FILES
# ==========================================================

COPY . .

# ==========================================================
# EXPOSE PORT
# ==========================================================

EXPOSE 8080

# ==========================================================
# HEALTHCHECK
# ==========================================================

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
CMD curl --fail http://localhost:8080/ || exit 1

# ==========================================================
# GUNICORN SETTINGS
# ==========================================================

ENV GUNICORN_CMD_ARGS="\
--workers=1 \
--worker-class=uvicorn.workers.UvicornWorker \
--bind=0.0.0.0:8080 \
--timeout=300 \
--keep-alive=5 \
--max-requests=500 \
--max-requests-jitter=50"

# ==========================================================
# START APPLICATION
# ==========================================================

CMD ["gunicorn", "app.main:app"]
