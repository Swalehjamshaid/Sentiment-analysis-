# Use the official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Set working directory
WORKDIR /app

# Copy only requirements first (better caching)
COPY requirements.txt .

# Upgrade pip and install dependencies in one step to reduce layers
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Install Playwright browsers
RUN playwright install chromium

# Environment variables
ENV PYTHONPATH=.
ENV PORT=8080

# Expose port
EXPOSE 8080

# Command to run the FastAPI app using Gunicorn + Uvicorn worker
CMD gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:8080 app.main:app
