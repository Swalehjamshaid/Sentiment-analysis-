# Use the official Microsoft Playwright image
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Standard environment setup
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# 1. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. Copy all application code
COPY . .

# 3. CRITICAL: This downloads the actual Chromium browser into the container
RUN playwright install chromium
RUN playwright install-deps chromium

# 4. Start command
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
