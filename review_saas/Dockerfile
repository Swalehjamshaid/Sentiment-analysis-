# ============================================
#  Playwright + FastAPI Production Dockerfile
# ============================================

# Use official Playwright Python image (includes browsers)
FROM mcr.microsoft.com/playwright/python:1.41.1-focal

# Set working directory
WORKDIR /app

# Better caching: copy only requirements first
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

# Create a non-root user for security
RUN useradd -m appuser
USER appuser

# Expose FastAPI port
EXPOSE 8080

# Environment variables (optional)
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8080

# Start FastAPI using Gunicorn + Uvicorn worker
# Increase timeout for Playwright (browser may take time)
CMD ["gunicorn", 
     "--workers", "1",
     "--worker-class", "uvicorn.workers.UvicornWorker",
     "--timeout", "120",
     "--bind", "0.0.0.0:8080",
     "app.main:app"]
