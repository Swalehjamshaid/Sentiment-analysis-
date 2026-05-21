# ==========================================================
# TRUSTLYTICS AI — RAILWAY PRODUCTION DOCKERFILE
# MAY 2026 STABLE ENTERPRISE VERSION
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
# ==========================================================

FROM python:3.11-slim

# ==========================================================
# PYTHON SETTINGS
# ==========================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ==========================================================
# WORK DIRECTORY
# ==========================================================

WORKDIR /app

# ==========================================================
# INSTALL SYSTEM DEPENDENCIES
# ==========================================================

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    wget \
    curl \
    unzip \
    git \
    xvfb \
    ca-certificates \
    fonts-liberation \
    xdg-utils \
    chromium \
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
    && rm -rf /var/lib/apt/lists/*

# ==========================================================
# COPY REQUIREMENTS
# ==========================================================

COPY requirements.txt .

# ==========================================================
# UPGRADE PIP
# ==========================================================

RUN pip install --upgrade pip setuptools wheel

# ==========================================================
# INSTALL PYTHON REQUIREMENTS
# ==========================================================

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================================
# INSTALL PLAYWRIGHT BROWSER
# ==========================================================

RUN playwright install chromium

# ==========================================================
# INSTALL CAMOUFOX
# ==========================================================

RUN python -m camoufox fetch

# ==========================================================
# CREATE PLAYWRIGHT CACHE
# ==========================================================

RUN mkdir -p /ms-playwright

# ==========================================================
# COPY PROJECT FILES
# ==========================================================

COPY . .

# ==========================================================
# CREATE TMP DIRECTORY
# ==========================================================

RUN mkdir -p /tmp

# ==========================================================
# EXPOSE PORT
# ==========================================================

EXPOSE 8080

# ==========================================================
# HEALTHCHECK
# ==========================================================

HEALTHCHECK CMD curl --fail http://localhost:8080 || exit 1

# ==========================================================
# START FASTAPI (PRODUCTION)
# ==========================================================

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
