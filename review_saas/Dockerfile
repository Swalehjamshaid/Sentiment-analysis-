# --- Base Image ---
FROM python:3.12-slim

# --- Set environment ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- System dependencies for Playwright and browsers ---
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libcups2 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango1.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# --- Set working directory ---
WORKDIR /app

# --- Copy requirements ---
COPY requirements.txt .

# --- Install Python dependencies ---
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Playwright browsers ---
RUN playwright install chromium

# --- Copy app code ---
COPY . .

# --- Expose port ---
EXPOSE 8080

# --- Command to run ---
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--workers", "1"]
