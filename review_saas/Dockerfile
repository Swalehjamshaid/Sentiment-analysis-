FROM mcr.microsoft.com/playwright/python:v1.45.0-noble

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy only the requirements file for now to test the next phase
COPY requirements.txt .

# Start command (we will refine this later)
CMD ["python", "main.py"]
