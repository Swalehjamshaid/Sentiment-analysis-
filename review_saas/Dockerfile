FROM python:3.11-slim

# 1. System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. Playwright Alignment (Fixed)
RUN mkdir -p /ms-playwright && chmod 777 /ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium --with-deps

# 4. App Code
COPY . .

# 5. Environment & Paths
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=8080

EXPOSE 8080

# 6. Start Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
