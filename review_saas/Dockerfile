# 1. Use a stable Python base
FROM python:3.11-slim

# 2. Install system dependencies for Postgres and Playwright
# We combine these to keep the image layer count low
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 3. Set the working directory
# All subsequent commands happen inside /app
WORKDIR /app

# 4. Install Python requirements
# We copy this first to allow Docker to cache the installation
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Playwright Alignment (Permission-Safe Version)
# We create the folder inside /app to avoid root-level permission errors
RUN mkdir -p /app/ms-playwright && chmod -R 777 /app/ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright

# Install only the Chromium browser and its system-level dependencies
RUN playwright install chromium --with-deps

# 6. Copy the application code
# This copies 'app/', 'main.py', etc., into /app/
COPY . .

# 7. Critical Environment Variables
# PYTHONPATH=/app ensures 'import app.core' works perfectly
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080

# 8. Expose the port
EXPOSE 8080

# 9. Start the application
# Using 'python3 -m uvicorn' is the safest way to resolve importlib errors
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
