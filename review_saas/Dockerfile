# 1. Use the official Playwright image as a base (SOLVES ALL DEPENDENCY ERRORS)
# This image already has the OS-level libs for Chromium/Firefox/Webkit
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# 2. Set the working directory
WORKDIR /app

# 3. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Critical: Playwright Browser Installation
# We only install the chromium binary because the OS libs are already there
# We use /app/ms-playwright to ensure we stay within writable space
RUN mkdir -p /app/ms-playwright && chmod -R 777 /app/ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright
RUN playwright install chromium

# 5. Copy application code
COPY . .

# 6. Environment & Paths
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080

EXPOSE 8080

# 7. Start the application
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
