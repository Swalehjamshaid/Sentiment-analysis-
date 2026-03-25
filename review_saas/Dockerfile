# =============================================
# Playwright + Python Docker Image (2026)
# =============================================
FROM python:3.11-slim-bookworm

# Install system dependencies required by Firefox (Playwright/Patchright)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download browsers (very important!)
RUN playwright install firefox --with-deps
# If you prefer patchright instead:
# RUN patchright install firefox --with-deps

# Copy your application code
COPY . .

# Expose FastAPI port
EXPOSE 8080

# Run with Gunicorn + Uvicorn worker
CMD ["gunicorn", "app.main:app", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
