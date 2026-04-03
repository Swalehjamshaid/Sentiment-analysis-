# ---------------------------------------------------------
# Playwright Python base image (includes browsers & deps)
# ---------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# ---------------------------------------------------------
# Environment variables
# ---------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

# ---------------------------------------------------------
# Set working directory
# ---------------------------------------------------------
WORKDIR /app

# ---------------------------------------------------------
# Install Python dependencies (cached layer)
# ---------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------
# Install Playwright browser (optional, safe recheck)
# Browsers are already included but this guarantees version
# ---------------------------------------------------------
RUN python3 -m playwright install chromium

# ---------------------------------------------------------
# Copy application code
# ---------------------------------------------------------
COPY . .

# ---------------------------------------------------------
# Expose service port
# ---------------------------------------------------------
EXPOSE 8080

# ---------------------------------------------------------
# Start application
# ---------------------------------------------------------
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
