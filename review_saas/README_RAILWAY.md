# Review SaaS — Railway Deployment

    ## 1) Create a Railway project
    - Add **PostgreSQL** to the project.
    - Add a service for this app (connect your GitHub or upload).

    ## 2) Set service variables
    - `SECRET_KEY` = a long random value
    - `DATABASE_URL` = (auto-injected by Railway when Postgres is linked). If not, paste the Postgres connection string.
    - Optional: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASS`, `FROM_EMAIL`
    - Optional: `GOOGLE_API_KEY`
    - Optional: `ENABLE_SCHEDULER` = 0 or 1

    ## 3) Start command
    - `uvicorn app.main:app --host 0.0.0.0 --port ${PORT}`

    ## 4) Test
    - After deploy, run the included `smoke_test.sh` against your Railway URL.