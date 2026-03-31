# Use the official Playwright Python image as the base
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Set the working directory
WORKDIR /app

# 1. Install essential system build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip to the latest version
RUN pip install --no-cache-dir --upgrade pip

# 3. INSTALL PYTORCH SEPARATELY (The Heavy Part)
# We do this first so it's cached and doesn't crash during the full requirements install
RUN pip install --no-cache-dir \
    --default-timeout=1000 \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.0 torchvision==0.17.0 torchaudio==2.2.0

# 4. Copy and install the rest of your requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 5. Copy the rest of your application code
COPY . .

# 6. Ensure Playwright browsers are installed (since we are in a Playwright image)
RUN playwright install --with-deps chromium

# 7. Start the application (adjust 'main.py' to your entry point file)
CMD ["python", "main.py"]
