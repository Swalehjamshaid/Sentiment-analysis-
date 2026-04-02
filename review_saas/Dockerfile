# =============================================
#   Review SaaS - Production Dockerfile (Error-Free)
#   Base: Official Playwright Python (Jammy)
# =============================================

FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# === 1. System Dependencies (Essential for Rust + kreuzberg + build tools) ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# === 2. Install Rust via rustup (required for kreuzberg) ===
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    . "$HOME/.cargo/env" && \
    rustup default stable

# Add Cargo to PATH for the current shell/session
ENV PATH="/root/.cargo/bin:${PATH}"

# === 3. Upgrade Python build tools + install maturin (for Rust-Python packages) ===
RUN pip install --no-cache-dir --upgrade pip setuptools wheel maturin

# === 4. Pre-install heaviest dependencies (improves caching & speed) ===

# Torch CPU-only (prevents accidental GPU wheels)
RUN pip install --no-cache-dir \
    torch==2.1.1 \
    torchvision==0.16.1 \
    torchaudio==2.1.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Heavy NLP base
RUN pip install --no-cache-dir \
    transformers \
    sentence-transformers

# === 5. Install project requirements (kreuzberg will now build successfully) ===
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# === 6. Copy application code ===
COPY . .

# === 7. Install Chromium browser (lightweight for scraping) ===
RUN playwright install chromium --with-deps

# Expose port (standard for most PaaS like Render, Railway, Fly.io)
EXPOSE 8000

# === 8. Production startup command ===
# Increased timeout for long-running AI agent / report generation tasks
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", \
     "app.main:app", "--bind", "0.0.0.0:${PORT:-8000}", "--timeout", "300"]
