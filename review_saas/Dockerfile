# 1. UPDATED: Using the exact version required by your library (v1.51.0)
FROM mcr.microsoft.com/playwright/python:v1.51.0-jammy

# 2. Environment Setup
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 3. Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy Application Code
COPY . .

# 5. Install the new Chromium Headless Shell
# This will now find the correct paths because the base image is v1.51.0
RUN playwright install chromium

# 6. Start Command (Ensure Railway Dashboard 'Start Command' is EMPTY)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "120"]
