FROM python:3.12-slim

# --- Set environment variables ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- System dependencies for Playwright ---
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
    libpango-1.0-0 \
    libxcb1 \
    unzip \
    libgdk-pixbuf2.0-0 \
    libjpeg-turbo8 \
    libx264-155 \
    libvpx6 \
    libwebp6 \
    fonts-unifont \
    libenchant1c2a \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# --- Set working directory ---
WORKDIR /app

# --- Copy requirements and install Python deps ---
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# --- Install Playwright ---
RUN pip install playwright
RUN playwright install

# --- Copy application code ---
COPY . .

# --- Expose port ---
EXPOSE 8080

# --- Start FastAPI app ---
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--workers", "1"]
