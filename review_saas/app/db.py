import os
    from sqlalchemy import create_engine
    from .core.config import settings

    url = settings.DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://") and "sslmode" not in url:
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}sslmode=require"

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        future=True,
        echo=False,
    )