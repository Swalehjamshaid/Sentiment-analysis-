# 1. Use the official Playwright image (v1.45.0-jammy is the stable one)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 2. Use a wildcard to find requirements.txt anywhere in the project
COPY **/requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "setuptools==68.2.2"

# 3. Copy all application code into the /app folder
COPY . .

# 4. This is the "Magic Line" that fixes the Executable missing error
RUN playwright install chromium

EXPOSE 8080
ENV PYTHONUNBUFFERED=1 PORT=8080

# 5. Start command - adjusted to find your app correctly in any folder structure
CMD ["sh", "-c", "PYTHONPATH=. gunicorn --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:8080 review_saas.app.main:app || gunicorn --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 300 --bind 0.0.0.0:8080 app.main:app"]
