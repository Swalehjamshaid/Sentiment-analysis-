FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080
# This is the magic line that fixes Line 11 imports
ENV PYTHONPATH=/ 

WORKDIR /

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything so the folder 'app' exists at the root
COPY . .

EXPOSE 8080

# This command allows you to leave the Railway dashboard 'Start Command' EMPTY
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
