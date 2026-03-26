# Use Playwright Python base image
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Set working directory
WORKDIR /app

# Copy and install requirements
COPY requirements.txt /app/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy the app code
COPY . /app/

# Add a non-root user
RUN useradd -m appuser
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8080

# Install Playwright browsers
RUN playwright install --with-deps

# Use shell form CMD so $PORT expands dynamically on Railway
CMD gunicorn --workers 1 \
             --worker-class uvicorn.workers.UvicornWorker \
             --timeout 120 \
             --bind 0.0.0.0:${PORT} \
             app.main:app
