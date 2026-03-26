# -----------------------------
# Playwright Python + Chromium Dockerfile
# -----------------------------

# Use official Playwright image (includes browsers + deps)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Environment settings
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install Chromium explicitly (ensure correct path)
RUN playwright install chromium --with-deps

# Start server
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
