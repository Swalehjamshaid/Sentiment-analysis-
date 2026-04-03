# --- Stage 1: Build Stage ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system dependencies required for building some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade core pip tools (as seen in your logs)
RUN pip install --upgrade --root-user-action=ignore pip setuptools wheel

# Copy only requirements to leverage Docker caching
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# --- Stage 2: Final Runtime Stage ---
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy the application code
# This ensures "app/main.py" exists as expected by your sys.path.insert(0, "/app")
COPY . /app/

# Expose the port (FastAPI default in your code is 8080)
EXPOSE 8080

# Start the application using Gunicorn with Uvicorn workers
# This is more robust for production than running 'python app/main.py'
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080"]
