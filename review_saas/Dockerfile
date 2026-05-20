# ==========================================================
# REVIEW INTEL AI — RAILWAY PRODUCTION DOCKERFILE
# FASTAPI + SELENIUMBASE + CHROMIUM
# ==========================================================

FROM python:3.11-slim

# ==========================================================
# PYTHON SETTINGS
# ==========================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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
    libgtk-3-0 \
    libu2f-udev \
    libvulkan1 \
    libglu1-mesa \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# ==========================================================
# COPY REQUIREMENTS
# ==========================================================

COPY requirements.txt .

# ==========================================================
# INSTALL PYTHON DEPENDENCIES
# ==========================================================

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

# ==========================================================
# COPY APPLICATION FILES
# ==========================================================

COPY . .

# ==========================================================
# EXPOSE PORT
# ==========================================================

EXPOSE 8080

# ==========================================================
# START APPLICATION
# ==========================================================

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
