# 1. Use the official Python image
FROM python:3.11-slim

# 2. Prevent logs from buffering
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 3. THE FIX: Install the "Bones" manually (No more Error 100)
# We use the modern names like 'fonts-unifont' instead of 'ttf-unifont'
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    curl \
    libnss3 \
    libnspr4 \
    libatk1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libcups2t64 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-unifont \
    fonts-wqy-zenhei \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Install the browser ONLY (No deps command here!)
RUN playwright install chromium

# 6. Copy project files
COPY . .

# 7. Start the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
