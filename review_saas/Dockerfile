# ===== Dockerfile for FastAPI + Playwright Scraper =====
# Base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# --- Install system dependencies required for Playwright ---
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
    && rm -rf /var/lib/apt/lists/*

# --- Set working directory ---
WORKDIR /app

# --- Copy requirements first for caching ---
COPY requirements.txt .

# --- Upgrade pip and install Python dependencies ---
RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Playwright and download browsers ---
RUN pip install --no-cache-dir playwright playwright-stealth
RUN playwright install chromium

# --- Copy project files ---
COPY . .

# --- Expose the port FastAPI will run on ---
EXPOSE 8080

# --- Command to start the server ---
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080", "--log-level", "info"]
