# Use official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# Copy app code
COPY . /app/

# Install Playwright browsers
RUN playwright install --with-deps

# Create non-root user
RUN useradd -m appuser
USER appuser

# Expose port (optional, Docker convention)
EXPOSE 8080

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Correct CMD: shell form allows $PORT expansion
CMD sh -c 'gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:${PORT} app.main:app'
