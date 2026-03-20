FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install ONLY existing, required system packages for Playwright/Chromium
# REMOVED: ttf-unifont and ttf-ubuntu-font-family (obsolete and causing crash)
# Added correct minimal set of libs + fonts that actually exist
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget curl gnupg \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation fonts-noto-color-emoji fonts-wqy-zenhei \
    fonts-freefont-ttf fonts-tlwg-loma \
    xfonts-scalable xfonts-utils xvfb \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake Chromium into the image (no --with-deps to avoid font crash)
# --no-shell skips unnecessary shell fallback
RUN playwright install chromium --no-shell

# Copy application code
COPY . .

# Start the app (Railway will override port with $PORT if needed)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
