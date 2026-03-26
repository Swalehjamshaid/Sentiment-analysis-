# 1. Use the Playwright 1.45.0 base image to match requirements
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Standard environment setup
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# 3. Install Python dependencies
# We copy requirements.txt first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy all application code
COPY . .

# 5. CRITICAL: Install the specific Chromium version for 1.45.0
# This command physically puts the browser in /usr/local/lib/python3.12/dist-packages/
RUN playwright install chromium
RUN playwright install-deps chromium

# 6. Start command using Gunicorn/Uvicorn
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
