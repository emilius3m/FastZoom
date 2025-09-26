import asyncio
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import select

# Add project path for imports
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.models.sites import ArchaeologicalSite
from app.core.config import get_settings

async def check_sites():
    """Check what sites are in the database"""

    # Get settings and create engine
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True
    )

    try:
        async with AsyncSession(engine) as session:
            # Query all sites
            stmt = select(ArchaeologicalSite).order_by(ArchaeologicalSite.name)
            result = await session.execute(stmt)
            sites = result.scalars().all()

            print("Sites in database:")
            print("-" * 50)

            if not sites:
                print("No sites found in database!")
            else:
                for site in sites:
                    print(f"ID: {site.id}")
                    print(f"Name: {site.name}")
                    print(f"Code: {site.code}")
                    print(f"Location: {site.location}")
                    print(f"Region: {site.region}")
                    print(f"Active: {site.is_active}")
                    print(f"Public: {site.is_public}")
                    print("-" * 30)

            print(f"Total sites: {len(sites)}")

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_sites())