# We use the official Playwright base because it contains the 
# necessary Linux libraries (libnss3, libgbm1, etc.)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Standard Python environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Install dependencies from your requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY . .

# =================================================================
# CRITICAL FIX: Use patchright instead of playwright
# This ensures the browser is installed in the specific folder
# that 'patchright==1.50.0' expects to find.
# =================================================================
RUN patchright install chromium

# Start command (Ensure Railway Dashboard 'Start Command' is EMPTY)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
