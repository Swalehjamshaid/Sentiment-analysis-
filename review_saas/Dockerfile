# filename: Dockerfile
FROM python:3.12-slim

# --------------------------
# 1️⃣ Environment Setup
# --------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

# 🔥 FIX: move into review_saas
WORKDIR /app/review_saas

# --------------------------
# 2️⃣ System Dependencies
# --------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --------------------------
# 3️⃣ Install Python Dependencies
# --------------------------
COPY requirements.txt /app/
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r /app/requirements.txt

# --------------------------
# 4️⃣ Copy App Source Code
# --------------------------
COPY . /app/

# --------------------------
# 5️⃣ Expose Port
# --------------------------
EXPOSE 8080

# --------------------------
# 6️⃣ Start App (NOW WORKS)
# --------------------------
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
