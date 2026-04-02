# 1. Official Playwright Base (Jammy)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Environmental Setup
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# 3. System Dependencies (Crucial: Added openssl and ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    python3-dev \
    openssl \
    libssl-dev \
    ca-certificates \
    libffi-dev \
    libbz2-dev \
    pandoc \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 4. Install LATEST Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# 5. Build Tools for Rust/Python bridge
RUN pip install --no-cache-dir --upgrade pip setuptools wheel maturin

# 6. Pre-install heavy dependencies to save build time
RUN pip install --no-cache-dir torch==2.1.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir transformers sentence-transformers

# 7. Install requirements (This is where kreuzberg lives)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 8. App Setup
COPY . .
RUN playwright install chromium

CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
