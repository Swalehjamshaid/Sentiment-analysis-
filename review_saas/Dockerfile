# =============================================
#   Review SaaS - Production Dockerfile
#   Base: Playwright + Python (Jammy)
# =============================================

FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Prevent Python buffering + bytecode + increase pip timeout
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies (build tools for Rust-based packages like kreuzberg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and core build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# === PRE-INSTALL HEAVY DEPENDENCIES (Critical for build speed & stability) ===

# 1. CPU-only Torch (prevents pulling huge GPU wheels)
RUN pip install --no-cache-dir \
    torch==2.1.1 \
    torchvision==0.16.1 \
    torchaudio==2.1.1 \
    --index-url https://download.pytorch.org/whl/cpu

# 2. Heavy NLP / Transformer stack
RUN pip install --no-cache-dir \
    transformers \
    sentence-transformers

# Copy and install requirements (now much faster)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install only Chromium browser (lighter than full browsers)
RUN playwright install chromium --with-deps

# Expose port (Render, Railway, Fly.io, etc. use $PORT)
EXPOSE 8000

# Production start command with reasonable timeout
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", \
     "app.main:app", "--bind", "0.0.0.0:${PORT:-8000}", "--timeout", "180"]
