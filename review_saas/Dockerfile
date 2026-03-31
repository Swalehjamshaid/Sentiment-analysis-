FROM mcr.microsoft.com/playwright/python:v1.45.0-noble

WORKDIR /app

# 1. Install system build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# 3. Pre-install Heavy AI Libraries (CPU Version)
# This prevents memory crashes during the full requirements install
RUN pip install --no-cache-dir \
    --default-timeout=1000 \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.1 torchvision==0.16.1 torchaudio==2.1.1

# 4. Copy and Install remaining dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 5. Copy the rest of your Sentiment Analysis code
COPY . .

# 6. Install Playwright browsers for scraping
RUN playwright install --with-deps chromium

# 7. Start the application
# Note: Ensure your entry file is named main.py or update accordingly
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:$PORT"]
