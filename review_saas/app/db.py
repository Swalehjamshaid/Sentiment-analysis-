import os
    from sqlalchemy import create_engine
    from dotenv import load_dotenv

    load_dotenv()

    url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    # Heroku/Railway sometimes provide 'postgres://' — SQLAlchemy expects 'postgresql://'
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Add sslmode=require for Postgres if not present (safe for Railway)
    if url.startswith("postgresql://") and "sslmode" not in url:
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}sslmode=require"

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        future=True,
        echo=False
    )