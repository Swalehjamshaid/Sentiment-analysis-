# ==========================================================
# TRUSTLYTICS AI — RAILWAY PRODUCTION DOCKERFILE
# MAY 2026 OPTIMIZED ENTERPRISE VERSION
#
# SUPPORTS:
# ✅ FASTAPI
# ✅ PLAYWRIGHT
# ✅ CAMOUFOX
# ✅ GOOGLE MAPS SCRAPING
# ✅ CHROMIUM
# ✅ STEALTH BROWSERS
# ✅ AI CHATBOT
# ✅ RAG SYSTEM
# ✅ PDF REPORTING
# ✅ RAILWAY DEPLOYMENT
# ✅ MEMORY OPTIMIZED
# ✅ LIGHTWEIGHT BUILD
# ==========================================================

FROM python:3.11-slim

# ==========================================================
# ENVIRONMENT VARIABLES
# ==========================================================

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DEBIAN_FRONTEND=noninteractive

# ==========================================================
# WORK DIRECTORY
# ==========================================================

WORKDIR /app

# ==========================================================
# INSTALL SYSTEM DEPENDENCIES
# ==========================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    wget \
    unzip \
    git \
    xvfb \
    ca-certificates \
    fonts-liberation \
    xdg-utils \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libx11-xcb1 \
    libxt6 \
    libxi6 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    libgtk-3-0 \
    libu2f-udev \
    libvulkan1 \
    libglu1-mesa \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg-dev \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ==========================================================
# UPGRADE PIP TO LATEST STABLE
# ==========================================================

RUN python -m pip install --upgrade \
    pip \
    setuptools \
    wheel

# ==========================================================
# COPY REQUIREMENTS FIRST
# ==========================================================

COPY requirements.txt .

# ==========================================================
# INSTALL PYTHON DEPENDENCIES
# ==========================================================

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================================
# INSTALL PLAYWRIGHT BROWSERS
# ==========================================================

RUN playwright install --with-deps chromium

# ==========================================================
# INSTALL CAMOUFOX BROWSER
# ==========================================================

RUN python -m camoufox fetch || true

# ==========================================================
# CREATE REQUIRED DIRECTORIES
# ==========================================================

RUN mkdir -p \
    /ms-playwright \
    /tmp \
    /app/logs \
    /app/uploads

# ==========================================================
# COPY APPLICATION FILES
# ==========================================================

COPY . .

# ==========================================================
# PORT
# ==========================================================

EXPOSE 8080

# ==========================================================
# HEALTHCHECK
# ==========================================================

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
CMD curl -f http://localhost:8080/ || exit 1

# ==========================================================
# GUNICORN SETTINGS
# ==========================================================

ENV GUNICORN_CMD_ARGS="\
--workers=2 \
--worker-class=uvicorn.workers.UvicornWorker \
--timeout=300 \
--keep-alive=5 \
--max-requests=1000 \
--max-requests-jitter=50 \
--bind=0.0.0.0:8080"

# ==========================================================
# START APPLICATION
# ==========================================================

CMD ["gunicorn", "app.main:app"]
