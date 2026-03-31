# Official Playwright Python image (best for apps using both Playwright + Selenium)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements first (better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (critical step - must come after pip install playwright)
RUN playwright install --with-deps chromium

# Copy the rest of your code
COPY . .

# Expose the port Railway / your app uses
EXPOSE 8080

# Replace this with your actual start command:
# For FastAPI + Uvicorn (recommended):
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

# Alternative examples:
# CMD ["python", "app.py"]
# CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
