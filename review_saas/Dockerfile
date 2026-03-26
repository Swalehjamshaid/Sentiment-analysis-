# -----------------------------------------------
# Production-ready Dockerfile for Playwright + FastAPI/Gunicorn
# -----------------------------------------------

# Use the official Playwright Python image (includes browsers + OS dependencies)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Environment settings
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Copy Python dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure headless Chromium is used in the scraper
# In your Python code: browser = await p.chromium.launch(headless=True)

# Start FastAPI server with Gunicorn + Uvicorn worker
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
