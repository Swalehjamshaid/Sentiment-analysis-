# ================================
# BASE IMAGE
# ================================
FROM python:3.11-slim

# ================================
# ENVIRONMENT VARIABLES
# ================================
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    POETRY_VIRTUALENVS_CREATE=false \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ================================
# SYSTEM DEPENDENCIES (MANUAL FIX)
# ================================
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
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
    fonts-liberation \
    libdbus-glib-1-2 \
    libasound2 \
    libgdk-pixbuf-xlib-2.0-0 \
    fonts-unifont \
    && rm -rf /var/lib/apt/lists/*

# ================================
# WORKDIR
# ================================
WORKDIR /app

# ================================
# COPY FILES
# ================================
COPY requirements.txt ./
COPY app ./app

# ================================
# INSTALL PYTHON
# ================================
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# ================================
# INSTALL ONLY CHROMIUM
# ================================
RUN playwright install chromium

# ================================
# EXPOSE PORT
# ================================
EXPOSE 8080

# ================================
# START SERVER
# ================================
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080", "--workers", "1"]
