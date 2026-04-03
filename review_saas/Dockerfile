# Copy requirements first
COPY requirements.txt .

# Upgrade pip and install dependencies with a timeout buffer
# Note: Using 'python -m pip' is more reliable inside Docker 
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt
