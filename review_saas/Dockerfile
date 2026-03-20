FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system dependencies + fonts needed by Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates curl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation fonts-noto-color-emoji \
    fonts-wqy-zenhei fonts-tlwg-loma fonts-freefont-ttf \
    xfonts-scalable xfonts-utils xvfb \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake Playwright Chromium browser into the image (no download at runtime)
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
