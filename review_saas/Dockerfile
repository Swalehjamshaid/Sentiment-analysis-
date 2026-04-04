# --- Base Image ---
FROM python:3.12-slim

# --- Set workdir ---
WORKDIR /app

# --- Install system dependencies ---
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# --- Copy project ---
COPY ./review_saas /app/review_saas
COPY requirements.txt /app/

# --- Install Python dependencies ---
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# --- Expose Port ---
EXPOSE 8080

# --- Run Uvicorn (Railway / Docker ready) ---
CMD ["uvicorn", "review_saas.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
