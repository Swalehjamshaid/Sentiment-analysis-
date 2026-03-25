# Use a Debian/Ubuntu-based image (recommended)
FROM python:3.11-slim-bookworm   # or python:3.11-bookworm

# Install system dependencies required by Playwright browsers
RUN apt-get update && apt-get install -y \
    curl \
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

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# IMPORTANT: Download the browsers + dependencies INSIDE the container
# Use patchright or playwright CLI — both work
RUN playwright install firefox --with-deps
# OR if you prefer patchright:
# RUN patchright install firefox --with-deps

# Copy your application code
COPY . .

# Expose port (your FastAPI port)
EXPOSE 8080

# Use gunicorn as before
CMD ["gunicorn", "app.main:app", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
