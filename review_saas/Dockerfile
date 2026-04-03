# 1. Use Python 3.12 Slim
FROM python:3.12-slim

# 2. Environment setup
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

# 3. Set Working Directory
WORKDIR /app

# 4. System Dependencies (for bcrypt/scikit-learn)
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy Application Code
# This copies everything from your local folder into /app in the container
COPY . .

# 7. THE FIX: Force Python to look in the current directory for 'main.py'
ENV PYTHONPATH=/app

# 8. Start Command
# Using the list format is more stable on Railway
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
