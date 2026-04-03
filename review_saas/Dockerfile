# 1. Use Python 3.12 Slim
FROM python:3.12-slim

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
# CRITICAL: This allows 'import app' to work from any directory
ENV PYTHONPATH=/

# 3. Set WORKDIR to the root (Not /app)
WORKDIR /

# 4. Install System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy Application Code into the /app folder
# Your local files (main.py, core/, etc.) go into /app/
COPY . /app/

# 7. Expose Port
EXPOSE 8080

# 8. THE FINAL COMMAND
# We point to 'app.main:app' while standing in the root (/)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
