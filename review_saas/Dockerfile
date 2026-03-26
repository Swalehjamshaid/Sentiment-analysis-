# ================================
# Base Image
# ================================
FROM python:3.12-slim

# ================================
# Set working directory
# ================================
WORKDIR /app

# ================================
# Install system dependencies
# ================================
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libcups2 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libxcb1 \
    unzip \
    libgdk-pixbuf2.0-0 \
    libjpeg-turbo8 \
    libx264-155 \
    libvpx6 \
    libwebp6 \
    fonts-unifont \
    libenchant1c2a \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# ================================
# Copy requirements
# ================================
COPY requirements.txt .

# ================================
# Upgrade pip & install Python deps
# ================================
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# ================================
# Install Playwright + Chromium
# ================================
RUN pip install playwright==1.45.0 playwright-stealth==1.0.6
RUN playwright install chromium

# ================================
# Copy application code
# ================================
COPY . .

# ================================
# Expose port
# ================================
EXPOSE 8080

# ================================
# Command to run your app
# ================================
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080"]
