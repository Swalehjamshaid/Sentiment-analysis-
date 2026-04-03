# filename: Dockerfile
# -------------------------------------------------------------------------------
# STABLE & FLEXIBLE DOCKERFILE (Updated: April 3, 2026)
# -------------------------------------------------------------------------------

FROM python:3.12-slim

# 1. Environment variables for immediate log visibility and pathing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# 2. System dependencies (Heavy layer - cached)
# Includes 'libpq-dev' for database and 'curl' for Railway health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Dependency Layer (The core of your build)
# Copying exactly the requirements file to ensure line 31 never fails again
COPY requirements.txt .

# Upgrade pip first, then install requirements with a timeout safety net
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 4. Configuration Layer (Optional files)
# This will try to copy config files if they exist, but won't crash if they don't
COPY .env* *.json *.yaml ./ 2>/dev/null || :

# 5. Application Layer (Copying your code last)
COPY . .

# 6. Runtime Setup
EXPOSE 8080

# 7. THE START COMMAND
# This handles the 'app.main:app' path correctly for your structure
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080 --log-level info"]
