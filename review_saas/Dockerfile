# --------------------------- Base Image ---------------------------
FROM python:3.12-slim

# --------------------------- Environment Variables ---------------------------
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
ENV PYTHONPATH=/app

# --------------------------- Working Directory ---------------------------
WORKDIR /app

# --------------------------- System Dependencies ---------------------------
# Added 'libmagic1' for python-magic and 'libpq-dev' for Postgres
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# --------------------------- Python Dependencies ---------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --------------------------- Copy Application Code ---------------------------
COPY . .

# --------------------------- Expose Port ---------------------------
EXPOSE 8080

# --------------------------- Final Command ---------------------------
# Note: FastAPI app is located at app/main.py, instance is 'app'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
