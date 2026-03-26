# ============================================
#  Playwright + FastAPI Production Dockerfile
# ============================================

# FIXED: Version downgraded to v1.45.0-noble to match your requirements.txt
FROM mcr.microsoft.com/playwright/python:v1.45.0-noble

WORKDIR /app

# Ensure we are copying the requirements from the correct subfolder
COPY review_saas/requirements.txt /app/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy all files into the container
COPY . /app/

# Expose the port Railway uses
EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

# FIXED: Updated the path to point to review_saas.app.main:app
CMD ["gunicorn", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "300", "--bind", "0.0.0.0:8080", "review_saas.app.main:app"]
