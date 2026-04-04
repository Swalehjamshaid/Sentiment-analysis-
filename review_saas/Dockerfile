# Base image
FROM python:3.12-slim

# Working directory
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy project files
COPY review_saas /app/review_saas

# Set working directory inside project
WORKDIR /app/review_saas

# Expose port
EXPOSE 8080

# Entry point
CMD ["uvicorn", "review_saas.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
