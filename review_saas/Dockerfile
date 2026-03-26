# Use the official Microsoft Playwright image
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Install dependencies from your updated requirements.txt (which now has playwright)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .

# =================================================================
# UPDATED FIX: Use 'playwright' instead of 'patchright'
# Since you removed patchright from requirements.txt, 
# this command must now be playwright.
# =================================================================
RUN playwright install chromium

# Start command
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
