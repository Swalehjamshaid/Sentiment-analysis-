# Use official slim Python 3.10 image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Set environment variables to avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies needed for Python packages, Playwright, Selenium, PDFs, image libs, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        curl \
        wget \
        git \
        unzip \
        ca-certificates \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
        libcups2 \
        libdrm2 \
        libxcomposite1 \
        libxrandr2 \
        libgtk-3-0 \
        libx11-xcb1 \
        libxtst6 \
        libnss3 \
        libxss1 \
        libasound2 \
        fonts-liberation \
        libdbus-glib-1-2 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libpangocairo-1.0-0 \
        && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Copy the rest of the application
COPY . .

# Install Playwright browsers (for Playwright to work)
RUN python -m playwright install --with-deps

# Expose the default FastAPI port
EXPOSE 8000

# Command to run the app using Uvicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000", "--workers", "1"]
