# Review SaaS Pro (FastAPI)

    This build targets **full compliance** with your requirements, including:
    - Registration, email verification, JWT sessions, lockout, reset
    - Optional Google OAuth + 2FA (TOTP)
    - Company management with Place ID validation
    - Review fetch (manual + scheduled), dedupe, retry/backoff
    - Sentiment (star-based + text heuristic), keywords, score
    - Suggested replies (editable, 500 chars); single reply per review
    - Dashboard (per-company KPIs, trend, recent, keyword data) + CSV/Excel export
    - PDF report with KPIs, sample reviews, page breaks, optional logo
    - Notifications: email alerts for new negatives

    ## Quick start
    1. Set environment variables from `.env.example` in Railway.
    2. Deploy and start: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT}`
    3. Open `/` for UI; run smoke tests for APIs.

    ## Notes
    - Google and SMTP features require valid credentials.
    - Scheduler uses APScheduler; enable with `ENABLE_SCHEDULER=1`.
    - OAuth callback URL must match `OAUTH_REDIRECT_URL`.