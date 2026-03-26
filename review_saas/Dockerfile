# -----------------------------------------------
# Production-ready Dockerfile for FastAPI + Playwright Scraper
# -----------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# Environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install Chromium browser (important step)
RUN playwright install chromium --with-deps

# Expose port
EXPOSE 8080

# Start Gunicorn with better logging so you can see the real error
CMD ["gunicorn", \
     "--log-level", "debug", \
     "-w", "1", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "app.main:app", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
