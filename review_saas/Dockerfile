# 1. Use the official Playwright image (Includes Python and Browser dependencies)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# 2. Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools

# 3. Copy only requirements first
COPY requirements.txt .

# 4. Install all dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the entire project into the /app folder
COPY . .

# 6. CRITICAL: Physically install the Chromium browser engine
RUN playwright install chromium

# 7. Set environment variables for the container
ENV PYTHONPATH=.
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# 8. Start the app (Hardcoded 8080 to stop the $PORT error)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "--timeout", "300", "--bind", "0.0.0.0:8080", "app.main:app"]
