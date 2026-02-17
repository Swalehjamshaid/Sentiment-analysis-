from app.db import engine
    from app.models import Base, User, Company, Review
    from sqlalchemy.orm import Session
    from datetime import datetime

    def seed():
        Base.metadata.create_all(bind=engine)
        with Session(engine) as s:
            if not s.query(User).first():
                u = User(full_name="Demo User", email="demo@example.com", password_hash="demo", status="active")
                s.add(u); s.flush()
                c = Company(owner_id=u.id, name="Demo Company", city="Lahore", status="active")
                s.add(c); s.flush()
                r = Review(company_id=c.id, text="Great service", rating=5, review_at=datetime.utcnow(), sentiment="positive", keywords="service,great")
                s.add(r)
                s.commit()
        print("Seed complete.")

    if __name__ == "__main__":
        seed()