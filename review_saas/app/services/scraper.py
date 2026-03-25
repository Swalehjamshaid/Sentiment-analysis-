# Base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install all required system dependencies for Chromium & Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxcomposite1 libxdamage1 libxrandr2 libx11-xcb1 libxss1 \
    libxshmfence1 libglib2.0-0 libgtk-3-0 fonts-liberation \
    libdbus-glib-1-2 libasound2 libgdk-pixbuf-xlib-2.0-0 \
    unzip fonts-dejavu-core fonts-dejavu-extra \
    ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching)
COPY requirements.txt .

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
RUN pip install -r requirements.txt

# Install Playwright and Chromium
RUN pip install playwright && \
    playwright install chromium --with-deps

# Copy application code
COPY app ./app

# Set environment variable for Playwright to store browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Expose port if your app runs a web server
EXPOSE 8000

# Start your app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
