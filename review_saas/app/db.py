from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base
from app.core.settings import settings_dict

# Requirement 10: PostgreSQL Engine
engine = create_engine(settings_dict()["SQLALCHEMY_DATABASE_URI"])

# Requirement 13: Session Management
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    """Requirement 12: DB Setup Script"""
    import app.models
    Base.metadata.create_all(bind=engine)
    print("Memory Initialized: Tables created on Railway.")
