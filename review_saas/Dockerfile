# 1. Use the official Python image
FROM python:3.11-slim

# 2. Prevent logs from buffering
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 3. THE FIX: Install the specific "Bones" for Chromium manually
# I have removed the broken 'ttf' fonts and replaced them with working 'fonts' packages
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    curl \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
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
    libasound2 \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-wqy-zenhei \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Install the browser ONLY (no deps)
# We already installed the deps manually in Step 3
RUN playwright install chromium

# 6. Copy project files
COPY . .

# 7. Start the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
