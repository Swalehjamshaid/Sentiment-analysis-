# --- Base image ---
FROM python:3.12-slim-bullseye

# --- Set working directory ---
WORKDIR /app

# --- System dependencies for Playwright and general utilities ---
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
    libgdk-pixbuf-2.0-0 \
    libjpeg62-turbo \
    libx264-dev \
    libvpx-dev \
    libwebp-dev \
    libenchant-2-2 \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# --- Copy requirements and install Python packages ---
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# --- Install Playwright and download browsers ---
RUN pip install playwright==1.45.0 playwright-stealth==1.0.6
RUN playwright install --with-deps

# --- Copy application code ---
COPY . .

# --- Set environment variables (optional, adjust as needed) ---
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# --- Command to start the application ---
CMD ["gunicorn", "app.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
