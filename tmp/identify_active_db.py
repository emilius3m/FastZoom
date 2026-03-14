
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models.stratigraphy import UnitaStratigrafica

async def check_db_file(file_path):
    url = f"sqlite+aiosqlite:///{file_path}"
    engine = create_async_engine(url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as session:
            result = await session.execute(select(UnitaStratigrafica.us_code))
            codes = [row[0] for row in result.all()]
            print(f"FILE: {file_path} | US CODES: {codes}")
    except Exception as e:
        print(f"FILE: {file_path} | ERROR: {e}")
    finally:
        await engine.dispose()

async def main():
    files = [
        "./archaeological_catalog.db",
        "./data/archaeological_catalog.db",
        "./archaeology.db"
    ]
    for f in files:
        await check_db_file(f)

if __name__ == "__main__":
    asyncio.run(main())
