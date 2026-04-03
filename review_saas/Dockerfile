FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

WORKDIR /app

# ✅ CRITICAL: Install ALL required system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ✅ Upgrade pip first (important for Python 3.12)
RUN pip install --upgrade pip setuptools wheel

# ✅ Copy requirements first (better caching)
COPY requirements.txt .

# ✅ Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy project
COPY . .

EXPOSE 8080

# ✅ Correct entry point
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
