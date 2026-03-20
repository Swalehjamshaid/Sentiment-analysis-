# 1. Base Image
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 2. Manual "Bones" for Debian Trixie (Debian 13)
# I have removed the broken 'ttf' fonts and used the 't64' library names
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl \
    libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2t64 \
    fonts-liberation fonts-noto-color-emoji fonts-unifont \
    fonts-wqy-zenhei xvfb \
    && rm -rf /var/lib/apt/lists/*

# 3. Python Setup
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Bake the Browser into the Image (Build Phase)
RUN playwright install chromium

# 5. Project Files
COPY . .

# 6. Final Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
