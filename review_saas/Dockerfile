# 1. Use the official Playwright image for v1.45.0 (Jammy is the correct tag for this version)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 2. Copy the requirements from the correct subfolder
COPY review_saas/requirements.txt /app/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# 3. Copy all application code
COPY . /app/

# 4. CRITICAL: Install the browser matching this version
RUN playwright install chromium

# 5. Expose the port
EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

# 6. Start command (Corrected for your folder structure)
CMD ["gunicorn", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "300", "--bind", "0.0.0.0:8080", "review_saas.app.main:app"]
