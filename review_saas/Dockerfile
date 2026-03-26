# ================================
# Dockerfile for Python 3.12 + Playwright
# Fixed for Debian Trixie + Chromium
# ================================

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright
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
    libgdk-pixbuf-xlib-2.0-0 \
    libjpeg62-turbo \
    libwebp7 \
    fonts-unifont \
    libenchant-2-2 \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy your requirements.txt
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and download browsers
RUN pip install --no-cache-dir playwright
RUN playwright install --with-deps

# Copy the application code
COPY . .

# Expose port for FastAPI / Uvicorn
EXPOSE 8080

# Start the app using Gunicorn + Uvicorn
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080"]
