# -----------------------------------------------
# Fixed Dockerfile for Playwright 1.58.0
# -----------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# CRITICAL: Install the correct browsers for this Playwright version
RUN playwright install chromium --with-deps

EXPOSE 8080

# Clean CMD (removed debug logging since app is starting)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
