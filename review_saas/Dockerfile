# 1. Use the official Playwright Python image (comes with everything we need)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 2. Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools

# 3. Copy only requirements first (to speed up builds)
COPY requirements.txt .

# 4. Install all dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your application code
COPY . .

# 6. Install the Chromium browser physically into the container
RUN playwright install chromium

# 7. Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

# 8. Start the application using Gunicorn
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "--timeout", "300", "--bind", "0.0.0.0:8080", "app.main:app"]
