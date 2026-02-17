from fastapi import APIRouter
    from sqlalchemy.orm import sessionmaker
    from ..db import engine
    from ..models import User, Company, Review

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/stats")
    def stats():
        with SessionLocal() as s:
            users = s.query(User).count()
            companies = s.query(Company).count()
            reviews = s.query(Review).count()
            return {"users": users, "companies": companies, "reviews": reviews}