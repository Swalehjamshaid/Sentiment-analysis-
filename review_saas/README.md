
# ReviewSaaS — FastAPI (Railway-ready)

## Deploy on Railway
1. Create a new Railway project and connect this repo/ZIP.
2. In **Project → Variables**, add at minimum:
   - `SECRET_KEY`
   - `JWT_SECRET`
   - `DATABASE_URL` (use async driver: `postgresql+asyncpg://user:pass@host:5432/db?sslmode=require`)
3. Railway will detect Python and the `Procfile` and start with:
   ```sh
   uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
   ```
4. Optional: Add `GOOGLE_MAPS_API_KEY`, `GOOGLE_PLACES_API_KEY`, etc.

## Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # and fill values
uvicorn app.main:app --reload
```

