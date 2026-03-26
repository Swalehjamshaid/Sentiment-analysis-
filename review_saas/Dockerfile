# 1. Use the official Playwright image (matches your requirements.txt)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# 3. Install Python dependencies
# Since we are using the Playwright image, 'pip install playwright' 
# is already done, but we install your requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy all application code
COPY . .

# 5. CRITICAL: Only install the browser (Dependencies are already in the image!)
# This avoids the "Package not available" errors you just saw.
RUN playwright install chromium

# 6. Start command
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
#
