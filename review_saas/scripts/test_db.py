
# filename: scripts/test_db.py
import asyncio
from app.core.db import get_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute("SELECT 1")
        print("DB OK", res.scalar())

if __name__ == "__main__":
    asyncio.run(main())
