# 1. Official Playwright Base (Jammy)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Add Cargo/Rust to the system PATH
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# 3. System Dependencies: Added pkg-config and libssl-dev
# These are required for 'kreuzberg' to compile its Rust components.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    libffi-dev \
    pandoc \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. THE CRITICAL FIX: Install LATEST Rust (Supports Edition 2024)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# 5. Core Python Prep
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 6. Checkpoint: Torch CPU (Heavy Model Support)
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 7. Checkpoint: NLP Models for Sentiment Analysis
RUN pip install --no-cache-dir transformers sentence-transformers

# 8. Install Aligned Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 9. Finalize Browser Engines
COPY . .
RUN playwright install chromium

# 10. Start Command
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
