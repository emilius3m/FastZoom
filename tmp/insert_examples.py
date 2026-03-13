
import asyncio
import uuid
from datetime import date
from sqlalchemy import select
from app.database.engine import AsyncSessionLocal
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria, TipoUSEnum
from app.models.users import User

async def insert_examples():
    site_id = "d2a63402-7376-42d5-aafd-829de8f6ebd0"
    
    async with AsyncSessionLocal() as session:
        # Get superuser to use as creator
        result = await session.execute(select(User).where(User.email == "superuser@admin.com"))
        user = result.scalar_one_or_none()
        
        if not user:
            print("Error: Superuser not found.")
            return
        
        user_id = user.id
        print(f"Using user {user.email} (ID: {user_id}) as creator.")

        # Check if examples already exist to avoid duplicates (using us_code)
        us_codes = ["US1001", "US1002"]
        usm_codes = ["USM2001", "USM2002"]
        
        # 1. Insert US Examples
        for code in us_codes:
            stmt = select(UnitaStratigrafica).where(
                UnitaStratigrafica.site_id == site_id, 
                UnitaStratigrafica.us_code == code
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                us = UnitaStratigrafica(
                    site_id=site_id,
                    us_code=code,
                    tipo=TipoUSEnum.POSITIVA.value if code == "US1001" else TipoUSEnum.NEGATIVA.value,
                    definizione="Strato di accumulo con frammenti ceramici" if code == "US1001" else "Fossa di scarico circolare",
                    localita="Settore A, Saggio I" if code == "US1001" else "Settore B, Saggio II",
                    affidabilita_stratigrafica="alta" if code == "US1001" else "media",
                    data_rilevamento=date(2023, 10, 15),
                    responsabile_compilazione="Mario Rossi" if code == "US1001" else "Anna Bianchi",
                    created_by=user_id,
                    descrizione="Esempio di unità stratigrafica creata automaticamente per dimostrazione."
                )
                session.add(us)
                print(f"Added {code}")
            else:
                print(f"{code} already exists")

        # 2. Insert USM Examples
        for code in usm_codes:
            stmt = select(UnitaStratigraficaMuraria).where(
                UnitaStratigraficaMuraria.site_id == site_id, 
                UnitaStratigraficaMuraria.usm_code == code
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                usm = UnitaStratigraficaMuraria(
                    site_id=site_id,
                    usm_code=code,
                    definizione="Muro in opera incerta" if code == "USM2001" else "Paramento in laterizio",
                    localita="Ambiente 3" if code == "USM2001" else "Prospetto Nord",
                    tecnica_costruttiva="Opus Incertum" if code == "USM2001" else "Laterizio",
                    affidabilita_stratigrafica="alta" if code == "USM2001" else "media",
                    data_rilevamento=date(2023, 10, 18),
                    responsabile_compilazione="Luigi Verdi" if code == "USM2001" else "Elena Neri",
                    created_by=user_id,
                    descrizione="Esempio di unità stratigrafica muraria created automatically per dimostrazione."
                )
                session.add(usm)
                print(f"Added {code}")
            else:
                print(f"{code} already exists")

        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(insert_examples())
