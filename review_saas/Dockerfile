# Official Playwright Python image (compatible with playwright==1.45.0)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# System dependencies for building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and configure timeouts for large downloads
RUN pip install --no-cache-dir --upgrade pip && \
    pip config set global.timeout 900 && \
    pip config set global.retries 10

# Copy requirements first for better caching
COPY requirements.txt .

# Install all dependencies with PyTorch CPU index
# This is the critical line for torch + torchvision + torchaudio
RUN pip install --no-cache-dir \
    --default-timeout=900 \
    --index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Install Playwright browsers (MUST come after pip install playwright)
RUN playwright install --with-deps chromium

# Copy your application code
COPY . .

EXPOSE 8080

# Start command — change "main:app" if your FastAPI app is in a different file or named differently
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
