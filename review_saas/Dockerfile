# 1. Use a stable, lightweight Python base
FROM python:3.10-slim

# 2. Set environment variables to keep Python clean and responsive
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 3. Install ONLY the essential system libraries
# libmagic1 is required by the 'python-magic' library in your requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. Set the working directory
WORKDIR /app

# 5. Install Python dependencies
# We do this before copying code to use Docker's cache layer
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application code
COPY . .

# 7. The Start Command
# Using 'python main.py' directly first is the best way to see the REAL error 
# if it crashes again. Once it works, we can switch back to Gunicorn.
CMD ["python", "app/main.py"]
