# Copy requirements first
COPY requirements.txt .

# Upgrade pip and install dependencies with a timeout buffer
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt
