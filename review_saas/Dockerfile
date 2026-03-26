# Base image with Python & Playwright
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy application code
COPY . /app/

# Install Playwright browsers (with dependencies)
RUN playwright install --with-deps

# Add non-root user
RUN useradd -m appuser
USER appuser

# Expose port for Railway
EXPOSE 8080

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# -------------------------------
# CMD: Railway-compatible start command
# -------------------------------
CMD ["sh", "-c", "gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:$PORT app.main:app"]
