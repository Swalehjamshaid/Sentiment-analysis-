# =============================================
# Railway Fixed Dockerfile - PORT Error Solved
# =============================================
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

# Install dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Firefox browser
RUN playwright install firefox --with-deps

# Copy your code
COPY . .

EXPOSE 8080

# THIS IS THE IMPORTANT FIX — uses shell form so $PORT expands
CMD sh -c "gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:\${PORT:-8080}"
