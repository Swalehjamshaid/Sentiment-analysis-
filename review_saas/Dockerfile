# 1. Use Python 3.12 Slim
FROM python:3.12-slim

# 2. Set necessary environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
ENV PYTHONPATH=/app

WORKDIR /app

# 3. Install System Dependencies
# Added 'libmagic1' for python-magic and 'libpq-dev' for Postgres
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy Application Code
COPY . .

# 6. Expose Port
EXPOSE 8080

# 7. Final Command
# This assumes your file is named main.py and the FastAPI instance is 'app'
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
