# 1. Use Python 3.12 for best compatibility with 2026 AI libraries
FROM python:3.12-slim

# 2. Set environment variables to ensure logs are sent to Railway immediately
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

WORKDIR /app

# 3. Install system dependencies (Required for bcrypt and scikit-learn)
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy your application code
COPY . .

# 6. Expose the port Railway expects
EXPOSE 8080

# 7. Start the application
# IMPORTANT: Replace 'main:app' with 'your_filename:app' if your file is not named main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
