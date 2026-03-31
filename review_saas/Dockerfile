# Use Noble to get Python 3.12 (required for Dash 3.x and latest NLP libs)
FROM mcr.microsoft.com/playwright/python:v1.45.0-noble

# Set working directory
WORKDIR /app

# 1. Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# 3. Pre-install heavy AI libs (matched to your requirements.txt)
RUN pip install --no-cache-dir \
    --default-timeout=1000 \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1

# 4. Install the rest of the requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 5. Copy app and install browsers
COPY . .
RUN playwright install --with-deps chromium

# 6. Start command using Gunicorn/Uvicorn
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:$PORT"]
