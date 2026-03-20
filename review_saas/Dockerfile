# 1. Start with Python
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 2. THE "BONES" - Install everything here once
# We use modern names like fonts-unifont to avoid the Error 100
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2t64 \
    fonts-liberation fonts-noto-color-emoji fonts-unifont \
    fonts-wqy-zenhei xvfb \
    && rm -rf /var/lib/apt/lists/*

# 3. THE "MUSCLES" - Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. THE "ENGINE" - Install the browser during BUILD
# This prevents the "Installing dependencies" message in Deploy Logs
RUN playwright install chromium

# 5. THE "BRAIN" - Copy your code last
COPY . .

# 6. START
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
