FROM python:3.11-slim

# ===============================
# Environment
# ===============================
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
ENV PYTHONPATH=/app

WORKDIR /app

# ===============================
# System Dependencies
# ===============================
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    libmagic1 \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ===============================
# Python Dependencies
# ===============================
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ===============================
# Application Code
# ===============================
COPY . .

EXPOSE 8080

# ===============================
# Run Application
# ===============================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
