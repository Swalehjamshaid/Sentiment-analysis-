# ==========================================
# REVIEW INTEL AI — COMPLETE RAILWAY DOCKERFILE
# ==========================================

FROM python:3.11-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Prevent Python buffering logs
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# ==========================================
# INSTALL SYSTEM DEPENDENCIES
# ==========================================

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    wget \
    curl \
    gnupg \
    unzip \
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
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# COPY REQUIREMENTS
# ==========================================

COPY requirements.txt .

# ==========================================
# INSTALL PYTHON PACKAGES
# ==========================================

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# INSTALL PLAYWRIGHT
# ==========================================



# ==========================================
# COPY PROJECT FILES
# ==========================================

COPY . .

# ==========================================
# EXPOSE PORT
# ==========================================

EXPOSE 8080

# ==========================================
# START FASTAPI APP
# ==========================================

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
