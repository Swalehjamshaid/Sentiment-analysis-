# 1. Official Playwright Base
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Environment Setup
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# 3. System Tools
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

# 4. Core Python Upgrades
RUN pip install --no-cache-dir --upgrade pip

# 5. Pre-install Torch (CPU Only) - This is a heavy step
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 6. Copy and Install Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Final App Copy
COPY . .

# 8. Browser Installation
RUN playwright install chromium

# 9. Start Command
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
