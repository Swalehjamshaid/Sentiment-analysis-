# filename: Dockerfile
FROM python:3.12-slim

# 1. Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# 2. System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Dependency Layer
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 4. Application Layer (This now handles ALL files including configs)
# We copy everything at once to avoid the "non-directory" error
COPY . .

# 5. Runtime Setup
EXPOSE 8080

# 6. The Start Command
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080 --log-level info"]
