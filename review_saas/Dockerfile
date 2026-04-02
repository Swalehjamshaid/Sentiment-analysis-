# 1. Use Playwright Base (Pre-built for browsers)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Performance Environment Variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 3. CRITICAL: Install system headers for Rust/SSL (Fixes Kreuzberg Line 30 error)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl pkg-config libssl-dev libffi-dev \
    pandoc tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. Step-by-Step Installation to prevent Memory Spikes
RUN pip install --upgrade pip setuptools wheel

# 5. CHECKPOINT 1: Math & Data Core (Strict Pins)
RUN pip install numpy==1.26.4 scipy==1.11.4 pandas==2.1.1 scikit-learn==1.3.2 polars

# 6. CHECKPOINT 2: The "Heavy" NLP Stack (CPU Only)
RUN pip install torch==2.1.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install transformers sentence-transformers

# 7. CHECKPOINT 3: Pydantic Fix (Install this BEFORE the AI agents)
RUN pip install "pydantic>=2.8.0" pydantic-settings

# 8. CHECKPOINT 4: Install the remaining 2026 Enterprise Stack
COPY requirements.txt .
RUN pip install -r requirements.txt

# 9. Finalize Browser & Code
COPY . .
RUN playwright install chromium

# 10. Start Command with 180s Strategic Timeout
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
