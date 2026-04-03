# 1. Base Image
FROM python:3.10-slim

# 2. Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 3. System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    build-essential \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. Work directory
WORKDIR /app

# 5. Install Python dependencies (optimized caching)
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy app
COPY . .

# 7. Expose port (important for Railway)
EXPOSE 8000

# 8. Start command (PRODUCTION READY ✅)
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]
