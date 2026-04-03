FROM python:3.11-slim

# 1. System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Set Workdir
# This is where the root of your project (review_saas) will live
WORKDIR /app

# 3. Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Playwright Setup
RUN mkdir -p /ms-playwright && chmod 777 /ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium --with-deps

# 5. Copy Application Code
# Ensure the 'app' folder is copied directly into /app
COPY . .

# 6. CRITICAL: Set PYTHONPATH
# This tells Python to look in /app for the 'app' module
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# 7. Use the Module execution syntax
# 'app.main:app' refers to: folder 'app' -> file 'main.py' -> variable 'app'
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
