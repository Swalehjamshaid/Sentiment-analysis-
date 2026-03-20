FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Clean, minimal deps — NO obsolete ttf packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget gnupg \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 \
    fonts-liberation fonts-noto-color-emoji fonts-wqy-zenhei \
    fonts-freefont-ttf \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install ONLY chromium — skip --with-deps to avoid font crash
RUN playwright install chromium --no-shell

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${PORT:-8080}"]
