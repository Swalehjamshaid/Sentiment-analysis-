# 1. Use an official Python base image
FROM python:3.11-slim

# 2. Set environment variables to prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set work directory
WORKDIR /app

# 4. Install SYSTEM dependencies (The "Bones")
# We do this here so it's cached and doesn't run every time you start
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    libgconf-2-4 \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libgconf-2-4 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxtst6 \
    fonts-liberation \
    libappindicator1 \
    libnss3 \
    lsb-release \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# 5. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Install Playwright Browsers (The "Muscle")
# This is the most important part! It installs them INTO the image.
RUN playwright install chromium
RUN playwright install-deps chromium

# 7. Copy project files
COPY . .

# 8. Start the application
# Use 0.0.0.0 so Railway can route traffic to it
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
