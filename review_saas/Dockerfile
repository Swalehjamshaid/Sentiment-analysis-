# --------------------------- Base Image ---------------------------
FROM python:3.12-slim

# --------------------------- Environment Setup ---------------------------
# Avoid Python buffering & reduce warnings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    SECRET_KEY="super-secret-key"

# --------------------------- Install System Dependencies ---------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    pkg-config \
    libcairo2-dev \
    libffi-dev \
    python3-dev \
    cmake \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --------------------------- Set Working Directory ---------------------------
WORKDIR /app

# --------------------------- Copy & Install Python Dependencies ---------------------------
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------- Copy App Code ---------------------------
COPY ./app ./app

# --------------------------- Expose Port ---------------------------
EXPOSE 8080

# --------------------------- Gunicorn + Uvicorn Startup ---------------------------
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120"]
