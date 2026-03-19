# 1. Use an official Python base image
FROM python:3.11-slim

# 2. Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Set work directory
WORKDIR /app

# 4. Install SYSTEM dependencies
# We install just the basics first
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. THE FIX: Install Playwright and its SYSTEM dependencies
# 'install-deps' will automatically find the right library names for your OS version
RUN playwright install chromium
RUN playwright install-deps chromium

# 7. Copy project files
COPY . .

# 8. Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
