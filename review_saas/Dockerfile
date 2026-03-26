# -----------------------------------------------
# Production-ready Dockerfile for FastAPI + Playwright Scraper
# -----------------------------------------------
# Use official Playwright Python image matching requirements.txt (v1.58.0)
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# ----------------------------
# Environment settings
# ----------------------------
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ----------------------------
# Set working directory
# ----------------------------
WORKDIR /app

# ----------------------------
# Copy and install dependencies
# ----------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----------------------------
# Copy application code
# ----------------------------
COPY . .

# ----------------------------
# Ensure Chromium is installed (safety step)
# ----------------------------
RUN playwright install chromium --with-deps

# ----------------------------
# Expose port
# ----------------------------
EXPOSE 8080

# ----------------------------
# Start Gunicorn + Uvicorn worker
# ----------------------------
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
