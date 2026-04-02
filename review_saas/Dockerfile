# 1. Official Playwright Base (Includes most system deps)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Environment Setup
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# 3. Essential System Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. Core Python Upgrades
RUN pip install --no-cache-dir --upgrade pip

# 5. PRE-INSTALL TORCH (CPU ONLY) 
# This prevents the 2GB GPU versions from being pulled, saving ~7 mins of build time.
RUN pip install --no-cache-dir torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1 --index-url https://download.pytorch.org/whl/cpu

# 6. Copy and Install Requirements (Leveraging Docker Cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Final App Copy
COPY . .

# 8. Browser Installation (Chromium only for scraping efficiency)
RUN playwright install chromium

# 9. Start Command with Enterprise Timeout (180s for heavy AI tasks)
CMD gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:$PORT --timeout 180
