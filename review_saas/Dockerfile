# ================================
# Dockerfile for Playwright + FastAPI
# ================================

# Use official Playwright Python image with all browsers pre-installed
FROM mcr.microsoft.com/playwright/python:1.41.1-focal

# Set working directory
WORKDIR /app

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# Expose port
EXPOSE 8080

# Start the FastAPI app using Gunicorn + Uvicorn worker
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080"]
