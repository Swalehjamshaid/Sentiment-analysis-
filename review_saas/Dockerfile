# Copy requirements first
COPY requirements.txt .

# Upgrade pip and install dependencies with a timeout buffer
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r requirements.txt
