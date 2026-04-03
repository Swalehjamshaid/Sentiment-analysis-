# Copy requirements first
COPY requirements.txt .

# Upgrade pip and install everything in one clean line
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir --default-timeout=100 -r requirements.txt
