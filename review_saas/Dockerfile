# Official Playwright Python image (best compatibility with your playwright==1.45.0)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install system build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements first (better caching)
COPY requirements.txt .

# Install all Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser (Chromium) + dependencies
RUN playwright install --with-deps chromium

# Copy the rest of your project
COPY . .

# Expose port (Railway default is usually 8080)
EXPOSE 8080

# Start command - Recommended for FastAPI
# Change "main:app" if your main file or FastAPI instance name is different
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
