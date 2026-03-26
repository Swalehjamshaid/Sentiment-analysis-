Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Finds requirements anywhere in the project
COPY **/requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# This is the line that fixes your "Executable doesn't exist" error
RUN playwright install chromium

COPY . .

EXPOSE 8080
ENV PYTHONUNBUFFERED=1 PORT=8080

# Fail-safe start command
CMD ["sh", "-c", "PYTHONPATH=. gunicorn --workers 1 --worker-class uvicorn.worker
