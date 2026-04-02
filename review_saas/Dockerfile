# 1. Use the official Playwright base (pre-configured for browsers)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Prevent Python from buffering and set timeouts
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# 3. Install essential build tools for Rust-based libraries (like Kreuzberg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. Upgrade core build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 5. CHECKPOINT 1: Pre-install the heaviest library (CPU-only Torch)
# This prevents 2GB+ of GPU data from being pulled in requirements.txt
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 6. CHECKPOINT 2: Pre-install the NLP stack
# These take the most memory/time; keeping them here prevents requirements.txt from timing out
RUN pip install --no-cache-dir transformers sentence-transformers

# 7. Install remaining requirements (Now very fast because heavy stuff is cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copy application code
COPY . .

# 9. Final Browser Check (Only Chromium for scraping efficiency)
RUN playwright install chromium

# 10. Start Command with 180s Timeout for Strategic AI Reports
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
