# Use the official Playwright Python image (includes all browser dependencies)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Set working directory
WORKDIR /app

# Install system build tools (needed for some packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# IMPORTANT: Install Playwright browsers (this fixes most build failures)
RUN playwright install --with-deps chromium

# Copy the rest of your application code
COPY . .

# Expose port (change if your app uses a different port, e.g. 8000 for FastAPI)
EXPOSE 8080

# Start command - replace "main.py" with your actual entry file
# Examples:
# - For plain Python: CMD ["python", "main.py"]
# - For FastAPI/Uvicorn: CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
CMD ["python", "app.py"]
