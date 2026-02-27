
# filename: README.md
# ReviewSaaS (app/)

## Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```
Open http://localhost:8080/dashboard

## Env (Railway compatible)
See `.env.railway` (for Railway) and `.env.example` for local.

## Endpoints
- Auth: POST /register, POST /login, POST /logout
- Views: GET /dashboard
- Dashboard APIs: /api/kpis, /api/orders/series?days=14, /api/category-mix, /api/activity
- Export: /api/export/activity.csv, /api/export/activity.xlsx
- Companies: POST /companies/create
- Google: /google/health, /google/sync
