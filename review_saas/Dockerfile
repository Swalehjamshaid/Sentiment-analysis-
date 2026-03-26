# 1. Use the official Playwright image
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 2. Copy requirements from the subfolder to the CURRENT WORKDIR (.)
COPY review_saas/requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# 3. Copy everything else
COPY . .

# 4. CRITICAL: Physically install the browser
RUN playwright install chromium

EXPOSE 8080

ENV PYTHONUNBUFFERED=1 PORT=8080

# 5. Start command
CMD ["gunicorn", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "300", "--bind", "0.0.0.0:8080", "review_saas.app.main:app"]
