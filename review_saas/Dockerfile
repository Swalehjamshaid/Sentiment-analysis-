# --- Stage 1: Build Stage ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system dependencies for C-extensions (like bcrypt/cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install wheel
RUN pip install --upgrade --root-user-action=ignore pip setuptools wheel

# Install dependencies to a local folder
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Final Runtime Stage ---
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
# Force Python to look at the root for the 'app' package
ENV PYTHONPATH=/

WORKDIR /

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy project files into the /app directory
# This ensures "from app.core import..." works correctly
COPY . /app/

# Expose the port defined in your main.py
EXPOSE 8080

# --- CRITICAL PRODUCTION CONFIGURATION ---
# 1. We use app.main:app because the folder is named 'app'
# 2. --timeout 120 gives your 'init_models' and 'reset_schema' time to finish
# 3. --workers 4 handles concurrent requests
# 4. --preload ensures the app boots before workers are forked
CMD ["gunicorn", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120", \
     "--preload", \
     "app.main:app"]
