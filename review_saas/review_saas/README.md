
# Reputation Management SaaS (FastAPI + Bootstrap + Chart.js)

This repository implements the full set of requirements you listed, including:

- User registration, email verification, secure login/logout, lockout, password reset, optional 2FA & Google OAuth hooks.
- Company management with Google Place ID validation and duplicate prevention.
- Google reviews fetching (API client), deduplication, storage up to 500 per company.
- Sentiment & keywords, star-based categories, score 0..1, edge handling for short/empty.
- AI-like suggested replies (templated), editable and length-limited.
- Dashboard APIs for KPIs, trends, keywords; responsive charts via Chart.js.
- PDF report generation (ReportLab).
- Optional admin stats, CSV/Excel export endpoints hooks.

## Getting Started

1. **Create & activate environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
2. **Run server**
   ```bash
   uvicorn app.main:app --reload
   ```
3. **Google API Key**: put your key in `.env` to enable validation/fetch. Without a key, related endpoints will return errors gracefully.

## DB
- Defaults to SQLite for development. Switch to Postgres for production by setting `DATABASE_URL`.

## Security
- Password hashing with bcrypt (passlib), JWT via cookie (httpOnly). HTTPS recommended in deployment.
- Input validation via Pydantic and server-side checks. Login attempts logged and lockout enforced.

## Mapping to Requirements
See `docs/REQUIREMENTS_CHECKLIST.md` for an item-by-item mapping.
