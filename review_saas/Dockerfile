# 1. Start with Python (LOCKED stable OS)
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 2. THE "BONES" - Install everything here once
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

# 3. THE "MUSCLES" - Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. THE "ENGINE" - Install browser during build (stable method)
RUN python -m playwright install chromium

# 5. THE "BRAIN" - Copy your code last
COPY . .

# 6. START
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
