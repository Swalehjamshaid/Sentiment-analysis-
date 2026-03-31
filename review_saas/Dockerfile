# Base Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by Python packages & Playwright
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    ffmpeg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango1.0-0 \
    libgtk-3-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Copy requirements.txt
COPY requirements.txt .

# Install Python dependencies with longer timeout
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Install Playwright browsers
RUN playwright install

# Copy application code
COPY . .

# Expose port for FastAPI
EXPOSE 8000

# Start the app using Gunicorn with Uvicorn worker
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
