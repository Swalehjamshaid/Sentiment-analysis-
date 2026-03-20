# 1. Start with stable Python
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 2. THE "BONES"
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 \
    libglib2.0-0 libgtk-3-0 \
    fonts-liberation fonts-noto-color-emoji fonts-unifont \
    fonts-wqy-zenhei xvfb \
    && rm -rf /var/lib/apt/lists/*

# 3. THE "MUSCLES"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 🔥 CRITICAL FIX: Disable Playwright dependency install
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true

# 4. THE "ENGINE"
RUN python -m playwright install chromium

# 5. THE "BRAIN"
COPY . .

# 6. START
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
