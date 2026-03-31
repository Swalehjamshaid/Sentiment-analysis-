# Use python slim image
FROM python:3.10-slim

# Create a non-root user
RUN useradd -m appuser
WORKDIR /app
USER appuser

# Copy requirements first
COPY requirements.txt .

# Install packages
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Copy rest of the app
COPY . .

# Expose and start
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
