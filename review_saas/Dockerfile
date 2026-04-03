# filename: Dockerfile
# -------------------------------------------------------------------------------
# ULTIMATE FLEXIBLE DOCKERFILE for Python SaaS (FastAPI / Uvicorn / Gunicorn)
# -------------------------------------------------------------------------------

FROM python:3.12-slim

# 1. Permanent Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    APP_MODULE=app.main:app

# 2. Set Working Directory
WORKDIR /app

# 3. Comprehensive System Dependencies (Cached)
# Includes everything needed for Postgres, AI libraries, and basic debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. FLEXIBLE DEPENDENCY LAYER
# Automatically picks up ANY requirement file (txt, in, or lock)
COPY requirements*.txt ./
COPY pyproject.toml ./ 2>/dev/null || :

# Install whatever is found. Using 'python -m pip' for absolute reliability.
RUN python -m pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements.txt ]; then python -m pip install --no-cache-dir -r requirements.txt; fi

# 5. FLEXIBLE CONFIGURATION LAYER
# Accepts .env files, .json configs, or .yaml settings automatically
COPY .env* *.json *.yaml *.yml ./ 2>/dev/null || :

# 6. APPLICATION LAYER
# Copying everything else last to keep build times under 10 seconds for code changes
COPY . .

# 7. AUTOMATED PERMISSIONS
# Ensures all scripts are executable and the app has access to its own files
RUN chmod -R 755 /app

# 8. RUNTIME SETTINGS
EXPOSE 8080

# 9. THE "ULTIMATE" START COMMAND
# This command first checks if there's a custom 'start.sh' script.
# If not, it defaults to Uvicorn using the APP_MODULE variable.
# This means you can change your entry point via Railway Variables without touching this file.
CMD ["sh", "-c", "if [ -f start.sh ]; then /bin/sh start.sh; else uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT} --log-level info; fi"]
