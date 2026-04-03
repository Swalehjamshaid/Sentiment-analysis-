# --- Base Image ---
FROM python:3.12-slim

# --- Environment Variables ---
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV PIP_NO_CACHE_DIR=1

# --- Set Workdir ---
WORKDIR /app

# --- System Dependencies ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# --- Copy Requirements ---
COPY requirements.txt .

# --- Install Dependencies ---
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# --- Copy App Source ---
COPY . .

# --- Expose Port ---
EXPOSE 8000

# --- Run App ---
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]
