# 1. Official Playwright Base (Pre-configured for browsers)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Prevent Python from buffering and set high-performance env vars
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# 3. CRITICAL SYSTEM DEPS: Added libssl, pkg-config, pandoc, and tesseract
# These are required for kreuzberg (Rust/OCR) and multi-page PDF generation.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    libffi-dev \
    pandoc \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. Upgrade core build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 5. CHECKPOINT 1: Pre-install CPU-only Torch (Saves ~7 mins)
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 6. CHECKPOINT 2: Pre-install the heavy NLP stack
RUN pip install --no-cache-dir transformers sentence-transformers

# 7. Install remaining requirements (Now stable and fast)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. Copy application code
COPY . .

# 9. Final Browser Check (Chromium only for efficiency)
RUN playwright install chromium

# 10. Start Command with Enterprise Timeout (180s for heavy AI tasks)
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
