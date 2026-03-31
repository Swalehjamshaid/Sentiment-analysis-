# Official Playwright Python image (matches your playwright==1.45.0)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install system dependencies + increase build reliability
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and set timeout + retries for large downloads
RUN pip install --no-cache-dir --upgrade pip && \
    pip config set global.timeout 600 && \
    pip config set global.retries 5

# Copy requirements first (maximizes Docker layer caching)
COPY requirements.txt .

# Install Python dependencies with increased timeout
RUN pip install --no-cache-dir \
    --default-timeout=600 \
    -r requirements.txt

# Install Playwright browsers (must run AFTER playwright pip package)
RUN playwright install --with-deps chromium

# Copy the rest of your code
COPY . .

EXPOSE 8080

# Recommended FastAPI start command (change "main:app" if your file/variable differs)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
