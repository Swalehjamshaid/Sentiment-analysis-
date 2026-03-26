# =================================================================
# 1. BASE IMAGE
# =================================================================
# Using the official Microsoft Playwright image for Python 3.11.
# This image is built on Ubuntu 22.04 (Jammy) and includes ALL 
# OS-level dependencies (glib, nss, nspr, atk, cups, dbus, etc.) 
# required for Chromium to run in a headless environment.
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# =================================================================
# 2. ENVIRONMENT CONFIGURATION
# =================================================================
# Prevents Python from writing .pyc files and ensures output is 
# flushed directly to the Railway logs in real-time.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Set the working directory inside the container
WORKDIR /app

# =================================================================
# 3. DEPENDENCY INSTALLATION
# =================================================================
# We copy only the requirements first to leverage Docker layer caching.
COPY requirements.txt .

# Upgrade pip and install all Python libraries from your requirements.txt.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =================================================================
# 4. APPLICATION SETUP
# =================================================================
# Copy the rest of your application code into the container.
COPY . .

# Install the Chromium browser binaries.
# NOTE: We do NOT need the --with-deps flag here because the 
# 'jammy' base image already has the system dependencies installed.
RUN playwright install chromium

# =================================================================
# 5. START COMMAND
# =================================================================
# We use Gunicorn with Uvicorn workers for production stability.
# -w 1: Limited to 1 worker to stay within Railway RAM limits during scraping.
# --timeout 120: Increased to 2 minutes to allow for deep infinite scrolling.
# --bind 0.0.0.0:8080: Matches the internal port Railway expects.
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--timeout", "120"]
