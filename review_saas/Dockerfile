# Use official Playwright image with Python
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements first (enables Docker caching)
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Install Playwright browsers (required for scraping)
RUN playwright install --with-deps

# Set environment variables for Railway
ENV PYTHONPATH=.
ENV PORT=8080

# Expose port
EXPOSE 8080

# Start the FastAPI app with Gunicorn + Uvicorn
CMD gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:8080 app.main:app
