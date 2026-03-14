
import asyncio
from sqlalchemy import select
from app.database.engine import AsyncSessionLocal
from app.models.sites import ArchaeologicalSite
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria

async def check_db():
    async with AsyncSessionLocal() as session:
        # Check sites
        sites = (await session.execute(select(ArchaeologicalSite.id, ArchaeologicalSite.name))).all()
        print(f"SITES: {sites}")
        
        # Check US
        us_count = (await session.execute(select(UnitaStratigrafica.us_code, UnitaStratigrafica.site_id))).all()
        print(f"US: {us_count}")
        
        # Check USM
        usm_count = (await session.execute(select(UnitaStratigraficaMuraria.usm_code, UnitaStratigraficaMuraria.site_id))).all()
        print(f"USM: {usm_count}")

if __name__ == "__main__":
    asyncio.run(check_db())
