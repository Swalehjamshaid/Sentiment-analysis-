# Use official Playwright image (includes browsers + deps)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Environment settings
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 🔥 CRITICAL FIX: Force correct browser path
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Ensure Chromium is installed
RUN playwright install chromium

# Start server
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
