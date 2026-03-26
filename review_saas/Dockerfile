# ✅ Use official Playwright image (already includes Chromium + deps)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# ✅ Environment settings
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 🔥 CRITICAL: Force correct browser path (fixes your error)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy full app
COPY . .

# ✅ Ensure Chromium is installed in correct path
RUN playwright install chromium

# ✅ Start server (Railway compatible)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
