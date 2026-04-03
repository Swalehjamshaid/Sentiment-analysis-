FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal, safe)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port
EXPOSE 8080

# Start app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
