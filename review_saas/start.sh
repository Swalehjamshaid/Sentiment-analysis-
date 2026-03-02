# File: start.sh
#!/bin/bash
# Start FastAPI app using uvicorn

# Ensure the PORT variable is used by Railway
PORT=${PORT:-8000}

# Activate virtual environment if needed (optional)
# source .venv/bin/activate

# Start the app
uvicorn review_saas.app.main:app --host 0.0.0.0 --port $PORT --reload
