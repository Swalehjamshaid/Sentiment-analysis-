
# ReviewSaaS (FastAPI)

**Features**: Registration + email verification, Google OAuth (Authlib), optional 2FA (pyotp), review fetching scheduler (APScheduler), CSV/XLSX exports, PDF report generator, dashboard KPIs, Alembic migrations.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Env (.env)
See `.env.sample` for all keys.

### Alembic
```bash
alembic upgrade head
```

### Railway/Render
Use the provided `Procfile`.
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
