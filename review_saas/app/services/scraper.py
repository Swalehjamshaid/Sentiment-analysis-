# Use Python slim as base for minimal image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install minimal system dependencies required for Chromium / Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    fonts-liberation libnss3 libx11-xcb1 libxcomposite1 \
    libxcursor1 libxdamage1 libxrandr2 libasound2 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libgbm1 libgtk-3-0 libpango-1.0-0 libxss1 libxtst6 \
    xdg-utils git unzip && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Install Playwright and Chromium with minimal deps
RUN pip install playwright && \
    playwright install --with-deps chromium

# Copy your application code
COPY app ./app

# Optional: environment variable for Playwright in Docker
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Expose port (adjust if needed)
EXPOSE 8000

# Start your app (adjust your command)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
