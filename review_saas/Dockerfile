FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

COPY . /app/

# Install Playwright browsers as root
RUN playwright install --with-deps

# Add non-root user
RUN useradd -m appuser
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8080

# Shell form CMD for Railway dynamic port
CMD gunicorn --workers 1 \
             --worker-class uvicorn.workers.UvicornWorker \
             --timeout 120 \
             --bind 0.0.0.0:${PORT} \
             app.main:app
