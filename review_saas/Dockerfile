# filename: Dockerfile
FROM python:3.12-slim

# 1. High-Level Environment Setup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# 2. System Dependencies (Cached unless you change the base image)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. FLEXIBLE REQUIREMENTS STEP
# We copy anything starting with 'requirement' (covers requirements.txt, requirements-dev.txt, etc.)
COPY requirements*.txt ./

# Install requirements. If you add a new file, it will be detected here.
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 4. ADDITIONAL CONFIG FILES STEP
# If you have extra config files (like firebase.json or settings.yaml), 
# they get copied here before the heavy code logic.
COPY *.json *.yaml *.yml ./ 2>/dev/null || :

# 5. FINAL CODE INJECTION
# Everything else (app folder, static, templates) is copied now.
COPY . .

# 6. Runtime Configuration
EXPOSE 8080

# sh -c allows us to use the PYTHONPATH variable reliably on Railway
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080 --log-level info"]
