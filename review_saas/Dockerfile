# Official Playwright Python image (matches playwright==1.45.0)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip + increase timeout/retries for large packages (torch, transformers)
RUN pip install --no-cache-dir --upgrade pip && \
    pip config set global.timeout 600 && \
    pip config set global.retries 5

# Copy requirements first for caching
COPY requirements.txt .

# Install dependencies with generous timeout
RUN pip install --no-cache-dir \
    --default-timeout=600 \
    -r requirements.txt

# Install Playwright browsers (must run after pip install playwright)
RUN playwright install --with-deps chromium

# Copy application code
COPY . .

EXPOSE 8080

# Start command (change "main:app" if your main file or app variable is different)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
