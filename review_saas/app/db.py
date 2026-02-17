import os
    from sqlalchemy import create_engine
    from dotenv import load_dotenv

    load_dotenv()

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
        echo=False,
        future=True,
    )