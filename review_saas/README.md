# Reputation Management SaaS (FastAPI + Bootstrap 5 + Chart.js)

    Scaffold generated for Khan Roy Jamshaid (Comp_HPK). This package includes a working FastAPI project with templates, routes, and services that align with the functional requirements you provided (registration, companies management, review fetching, sentiment, suggested replies, dashboard KPIs, and PDF report export).

    ## Quick Start
    1. Create and activate a virtualenv (Python 3.10+).
    2. Copy `.env.example` → `.env` and set values.
    3. Install deps: `pip install -r requirements.txt`.
    4. Run app: `uvicorn app.main:app --reload`.
    5. Open http://127.0.0.1:8000/.

    ## Structure
    ```
    app/
      core/settings.py        # Central config (Pydantic Settings)
      db.py                   # SQLAlchemy engine & session
      models.py               # SQLAlchemy models
      schemas.py              # Pydantic schemas
      utils/security.py       # Hashing, JWT, helpers
      scheduler.py            # Background scheduler hook (stub)
      routes/
        auth.py, companies.py, reviews.py, reply.py, reports.py, dashboard.py, home.py
      services/
        google_places.py, sentiment.py, reply.py, pdf_report.py, email.py,
        record.py, grader.py  # per your prior preferences
      templates/
        base.html, home.html, auth.html, companies.html, dashboard.html
      static/css/style.css
    ```

    ## Notes
    - External integrations (Google Places, email, PDF) are stubbed with safe fallbacks so the app can run without credentials.
    - Database is SQLite by default; upgrade to Postgres in prod.
    - Chart.js assets are included via CDN in `base.html`.
    - Dark/Light theme toggle is built into the base layout.