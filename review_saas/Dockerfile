# 1. Use the official Playwright base
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Prevent Python from buffering and set timeouts
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# 3. FIX: Added pkg-config and libssl-dev (Required for kreuzberg/Rust compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Upgrade core build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 5. CHECKPOINT 1: Pre-install CPU-only Torch
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 6. CHECKPOINT 2: Pre-install the NLP stack
RUN pip install --no-cache-dir transformers sentence-transformers

# 7. Install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copy application code
COPY . .

# 9. Final Browser Check
RUN playwright install chromium

# 10. Start Command
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
