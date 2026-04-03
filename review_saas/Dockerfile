# filename: Dockerfile
FROM python:3.12-slim

# 1. Force the paths to be absolute and clear
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# 2. Essential system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Install dependencies (Cached)
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# 4. The Critical Change: Copying everything directly
# This ensures that /app/app/main.py exists exactly where expected
COPY . .

# 5. Runtime Setup
EXPOSE 8080

# 6. The Command that works on Railway
# We use the full path to avoid any "frozen importlib" confusion
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
