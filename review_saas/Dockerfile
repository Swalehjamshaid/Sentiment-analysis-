# ================================
# 1. BASE IMAGE
# ================================
FROM python:3.11-slim

# ================================
# 2. ENVIRONMENT CONFIG
# ================================
ENV PYTHONUNBUFFERED=1 \
    # Force Playwright to store browsers in a consistent location
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    # Optimize memory for Railway
    MALLOC_ARENA_MAX=2

# ================================
# 3. SYSTEM DEPENDENCIES
# ================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxcomposite1 libxdamage1 libxrandr2 libx11-xcb1 \
    libxss1 libxshmfence1 libglib2.0-0 libgtk-3-0 \
    libdbus-glib-1-2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ================================
# 4. PYTHON INSTALLATION
# ================================
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ================================
# 5. BROWSER INSTALLATION
# ================================
# This MUST be done during the build phase
RUN playwright install --with-deps chromium

# ================================
# 6. APPLICATION CODE
# ================================
COPY . .

# ================================
# 7. START COMMAND
# ================================
EXPOSE 8080
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120"]
