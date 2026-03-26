# 1. Use the official Playwright image (guarantees the right OS for browsers)
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 2. Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# 3. Install Python dependencies
# Because the Root is "/", we point to the folder for the requirements file
COPY review_saas/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy all application code from the root
COPY . .

# 5. CRITICAL: Physically install the Chromium browser engine
# This is the step that fixes the "Executable doesn't exist" error
RUN playwright install chromium
RUN playwright install-deps chromium

# 6. Start command (Corrected path to find your main.py from the new root)
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "review_saas.app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "300"]
