import asyncio
from app.database import AsyncSessionLocal, engine, Base
from app import models
from app.auth.security import get_password_hash
from sqlalchemy import select

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        email = "demo@example.com"
        q = await db.execute(select(models.User).where(models.User.email==email))
        if not q.scalar_one_or_none():
            user = models.User(name="Demo User", email=email, password_hash=get_password_hash("demo123"), is_admin=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            comp = models.Company(user_id=user.id, name="Demo Company", google_place_id="ChIJN1t_tDeuEmsRUsoyG83frY4", city="Sydney", contact_email="support@example.com", contact_phone="+61-2-0000-0000")
            db.add(comp)
            await db.commit()
            print("Seeded demo user demo@example.com / demo123 and a company.")
        else:
            print("Demo user already exists")

if __name__ == "__main__":
    asyncio.run(main())