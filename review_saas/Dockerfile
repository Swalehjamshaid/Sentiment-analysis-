# 1. Using the official Playwright image (includes browsers & system deps)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# 3. Essential build tools only
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. Upgrade pip first for better dependency resolution
RUN pip install --no-cache-dir --upgrade pip

# 5. OPTIMIZATION: Pre-install Torch CPU ONLY
# This prevents the 2GB GPU versions from being pulled by transformers/sentence-transformers
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 6. Copy requirements separately to leverage Docker Caching
COPY requirements.txt .

# 7. Install requirements (This will now be FAST because Torch is already there)
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 8. Copy the rest of the app
COPY . .

# 9. Final browser check (Playwright image has them, but this ensures Chromium is ready)
RUN playwright install chromium

# 10. Start command with proper path and timeout for heavy AI tasks
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
