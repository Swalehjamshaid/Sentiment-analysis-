# Use the official Playwright image
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Install the browser engine
RUN playwright install chromium

# Set the environment
ENV PYTHONPATH=.
ENV PORT=8080

EXPOSE 8080

# FIXED START COMMAND: No brackets to avoid the "cmd not found" error
CMD gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:8080 app.main:app
