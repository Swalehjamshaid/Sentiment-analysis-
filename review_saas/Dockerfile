# 1. Use the Playwright-ready base image (saves 5-10 minutes of build time)
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# 2. Set working directory
WORKDIR /app

# 3. Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Break the circle: Create directory and set ENV BEFORE installation
RUN mkdir -p /app/ms-playwright && chmod -R 777 /app/ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright

# 5. Use 'python3 -m' to ensure the correct environment is used
RUN python3 -m playwright install chromium --with-deps

# 6. Copy application code
COPY . .

# 7. Final Environment Setup
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080

EXPOSE 8080

# 8. Start with module flag
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
