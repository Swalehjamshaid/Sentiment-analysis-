# ==========================================================
# TRUSTLYTICS AI — RAILWAY STABLE DOCKERFILE
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
# WORKDIR
# ==========================================================

WORKDIR /app

# ==========================================================
# SYSTEM PACKAGES
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
# INSTALL PYTHON PACKAGES
# ==========================================================

RUN pip install --upgrade pip setuptools wheel

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================================
# CREATE DIRECTORIES
# ==========================================================

RUN mkdir -p \
    /tmp \
    /app/logs \
    /app/uploads

# ==========================================================
# COPY PROJECT
# ==========================================================

COPY . .

# ==========================================================
# EXPOSE PORT
# ==========================================================

EXPOSE 8080

# ==========================================================
# HEALTHCHECK
# ==========================================================

HEALTHCHECK CMD curl --fail http://localhost:8080/health || exit 1

# ==========================================================
# START COMMAND
# ==========================================================

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --log-level debug"]
