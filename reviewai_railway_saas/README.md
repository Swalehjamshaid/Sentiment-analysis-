# Review Management & AI Response SaaS

A FastAPI + Bootstrap SaaS that fetches Google reviews, classifies sentiment, generates suggested replies, shows dashboards with Chart.js, and exports professional PDF reports. Built to deploy on **Railway**.

## Quickstart (Local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/seed_sample_data.py
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Deploy to Railway

- Push this repo to GitHub.
- In Railway: **New Project → Deploy from GitHub**. Railway will use `railway.json` (Nixpacks) and run Hypercorn.
- Set environment variables from `.env.example` in the Railway dashboard.
- Generate a public domain in **Settings → Networking**.

## Google Reviews – Important

- **Places API** returns only a small, non‑paginated set of public reviews (commonly *up to 5*). Use it for a sample and public rating totals.
- To fetch **all reviews and reply programmatically**, integrate the **Google Business Profile APIs** (requires OAuth and ownership of the location).

This code ships with both flows scaffolded: `services/google_reviews.py` has a Places API fetcher and a placeholder for GBP.

## Features

- Email/password auth (JWT), private dashboards.
- Add companies (name + Google Place ID or Maps link).
- Fetch reviews via Places API; sentiment = Positive/Neutral/Negative by star rating; naive keyword extraction.
- Suggested replies generated automatically; user can edit and store them (API prepared).
- Dashboard: KPIs, trend, and sentiment doughnut (Chart.js).
- PDF export with KPIs, sentiment bar, sample reviews & replies (ReportLab).
- Optional simple admin overview.

## Config

See `.env.example`. Minimum for fetching: `GOOGLE_MAPS_API_KEY` and a `google_place_id` on the company.

## Notes

- Password reset and Google OAuth are stubbed for MVP.
- For scheduled fetches/alerts, integrate APScheduler (scheduler is started in `main.py`).
- For production, switch DB to PostgreSQL and add HTTPS/CSRF on forms if you build a full server-rendered UI.

## License
MIT