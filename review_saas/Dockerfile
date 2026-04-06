# filename: Dockerfile

# 1. THE MANDATORY START
FROM python:3.12-slim

# 2. THE ENVIRONMENT ALIGNMENT
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 3. SETTING THE WORKDIR
WORKDIR /app

# 4. SYSTEM DEPENDENCIES
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. INSTALLING REQUIREMENTS
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. COPYING YOUR CODE
COPY . .

# 7. THE START COMMAND
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
