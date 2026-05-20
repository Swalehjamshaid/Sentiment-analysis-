# ==========================================================
# REVIEW INTEL AI — RAILWAY PRODUCTION DOCKERFILE
# FASTAPI + CAMOUFOX + PLAYWRIGHT + FIREFOX
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
    wget \
    curl \
    unzip \
    xvfb \
    ca-certificates \
    fonts-liberation \
    xdg-utils \
    firefox-esr \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libdbus-glib-1-2 \
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
    libxcb-dri3-0 \
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
# INSTALL PLAYWRIGHT FIREFOX
# ==========================================================

RUN playwright install firefox

# ==========================================================
# INSTALL PLAYWRIGHT SYSTEM DEPS
# ==========================================================

RUN python -m playwright install-deps

# ==========================================================
# INSTALL CAMOUFOX BROWSER
# ==========================================================

RUN python -m camoufox fetch

# ==========================================================
# COPY PROJECT FILES
# ==========================================================

COPY . .

# ==========================================================
# EXPOSE PORT
# ==========================================================

EXPOSE 8080

# ==========================================================
# START FASTAPI
# ==========================================================

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
