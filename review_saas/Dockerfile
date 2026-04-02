# =============================================
#   Review SaaS - Production Dockerfile (Fixed)
#   Base: Playwright + Python (Jammy)
# =============================================

FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# === Install system dependencies (CRITICAL for kreuzberg + Rust crates) ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and core build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# === PRE-INSTALL HEAVY DEPENDENCIES (for cache efficiency) ===

# 1. CPU-only Torch
RUN pip install --no-cache-dir \
    torch==2.1.1 \
    torchvision==0.16.1 \
    torchaudio==2.1.1 \
    --index-url https://download.pytorch.org/whl/cpu

# 2. Heavy NLP stack
RUN pip install --no-cache-dir \
    transformers \
    sentence-transformers

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install only Chromium (lighter)
RUN playwright install chromium --with-deps

EXPOSE 8000

# Production command
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", \
     "app.main:app", "--bind", "0.0.0.0:${PORT:-8000}", "--timeout", "180"]
