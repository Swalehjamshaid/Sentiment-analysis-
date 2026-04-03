# Use a modern Python version for 2026 compatibility
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install system dependencies required for building C extensions (bcrypt, scikit-learn)
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port Railway uses (usually 8080)
EXPOSE 8080

# Start the application using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.12", "--port", "8080"]
