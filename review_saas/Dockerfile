# 1. Use a stable Python 3.12 image
FROM python:3.12-slim

# 2. Prevent Python from buffering and creating .pyc files
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
# 3. CRITICAL: Tells Python to find the 'app' folder from the root
ENV PYTHONPATH=/

# 4. Set the working directory to the project root
WORKDIR /

# 5. Install system requirements for Postgres and python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 6. Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 7. Copy your entire project (including the /app folder)
COPY . .

# 8. Expose the Railway port
EXPOSE 8080

# 9. The default command (Keep Railway dashboard's Start Command EMPTY)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
