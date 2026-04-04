# Use official Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies for Postgres and building packages
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for cache efficiency)
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY ./review_saas /app/review_saas

# Expose port for FastAPI
EXPOSE 8080

# Run the app
CMD ["uvicorn", "review_saas.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
