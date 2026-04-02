# 1. Official Playwright Base
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Performance Environment Variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# 3. CRITICAL SYSTEM DEPS: Fixed for Rust Edition 2024
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    libffi-dev \
    pandoc \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. INSTALL LATEST RUST (Fixes Edition 2024 Error)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
# The PATH env variable in Step 2 ensures 'cargo' is visible now.

# 5. Upgrade core build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 6. CHECKPOINT 1: Pre-install CPU-only Torch
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 7. CHECKPOINT 2: Pre-install the heavy NLP stack
RUN pip install --no-cache-dir transformers sentence-transformers

# 8. Install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 9. Final Browser Check
RUN playwright install chromium

# 10. Start Command
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
