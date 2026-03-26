# ===============================
# Dockerfile for FastAPI + Playwright
# ===============================

# Base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright browsers
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
    libjpeg62-turbo \
    libx264-160 \
    libvpx6 \
    libwebp7 \
    fonts-unifont \
    libenchant-2-2 \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers with dependencies
RUN playwright install --with-deps

# Copy the rest of your application code
COPY . .

# Expose port
EXPOSE 8080

# Start FastAPI with Gunicorn and Uvicorn worker
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080"]
