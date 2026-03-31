FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 1. Install system-level dependencies first
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# 3. Copy only requirements to leverage Docker cache
COPY requirements.txt .

# 4. Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your app
COPY . .

# 6. Railway expects a start command
CMD ["python", "main.py"]
