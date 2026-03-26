# -------------------- Base Image --------------------
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

# -------------------- Working Directory --------------------
WORKDIR /app

# -------------------- Copy Requirements --------------------
COPY requirements.txt /app/

# -------------------- Install Python Dependencies --------------------
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# -------------------- Copy App Code --------------------
COPY . /app/

# -------------------- Install Playwright Browsers --------------------
# Must run as root here, because playwright install requires it
RUN playwright install --with-deps

# -------------------- Create Non-root User --------------------
RUN useradd -m appuser
USER appuser

# -------------------- Environment Variables --------------------
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# -------------------- Expose Port --------------------
EXPOSE 8080

# -------------------- Start Command (Shell form) --------------------
# Railway automatically sets $PORT, shell form ensures expansion
CMD sh -c 'gunicorn -w 1 -k uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:$PORT app.main:app'
