# Use Python 3.11 slim for a smaller, faster image
FROM python:3.11-slim

# 1. Install system dependencies
# Includes libpq for Postgres and dependencies for Playwright/Browsers
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Set the working directory
# We set this to /app. Your code will live in /app/app
WORKDIR /app

# 3. Install Python dependencies
# Copy requirements first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Install Playwright Browsers
# Based on your variable: PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium --with-deps

# 5. Copy the application code
# This copies your 'app' folder into '/app/app'
# This is CRITICAL for 'import app.core' to work.
COPY . .

# 6. Set Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 7. Expose the port from your variables
EXPOSE 8080

# 8. Start the application
# We use the module string so Python treats 'app' as a package
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
