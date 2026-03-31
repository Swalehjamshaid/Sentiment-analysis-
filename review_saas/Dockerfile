FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir --default-timeout=1000 --index-url https://download.pytorch.org/whl/cpu torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt
COPY . .
RUN playwright install --with-deps chromium

# FIXED LINE BELOW: Removed brackets to allow $PORT to work and added timeout for AI loading
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT --timeout 120
