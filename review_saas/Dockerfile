# --- Base image ---
FROM python:3.12-slim

# --- Set environment variables ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- System dependencies for Playwright and FastAPI ---
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
    && rm -rf /var/lib/apt/lists/*

# --- Set working directory ---
WORKDIR /app

# --- Copy requirements first for caching ---
COPY requirements.txt .

# --- Install Python dependencies ---
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# --- Install Playwright browsers ---
RUN pip install playwright
RUN playwright install --with-deps

# --- Copy application code ---
COPY . .

# --- Expose the FastAPI port ---
EXPOSE 8080

# --- Run the application with Gunicorn + Uvicorn ---
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080", "--workers", "1"]
