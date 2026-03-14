
import asyncio
import uuid
from datetime import date
from sqlalchemy import select
from app.database.engine import AsyncSessionLocal
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria, TipoUSEnum
from app.models.users import User
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

async def insert_examples():
    site_id = "d2a63402-7376-42d5-aafd-829de8f6ebd0"
    db_path = "./data/archaeological_catalog.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        # Get superuser
        result = await session.execute(select(User).where(User.email == "superuser@admin.com"))
        user = result.scalar_one_or_none()
        if not user:
            print("Error: Superuser not found.")
            return
        user_id = user.id

        # Data for US
        us_data = [
            {
                "us_code": "US1001",
                "tipo": TipoUSEnum.POSITIVA.value,
                "definizione": "Strato di accumulo con frammenti ceramici",
                "localita": "Settore A, Saggio I",
                "area_struttura": "Area Nord",
                "periodo": "Romano",
                "fase": "Fase I",
                "affidabilita_stratigrafica": "alta",
                "data_rilevamento": date(2023, 10, 15),
                "responsabile_compilazione": "Mario Rossi",
                "descrizione": "Esempio di unità stratigrafica positiva.",
                "interpretazione": "Riempimento di fossa",
                "colore": "Marrone scuro",
                "consistenza": "compatta"
            },
            {
                "us_code": "US1002",
                "tipo": TipoUSEnum.NEGATIVA.value,
                "definizione": "Fossa di scarico circolare",
                "localita": "Settore B, Saggio II",
                "area_struttura": "Area Sud",
                "periodo": "Romano",
                "fase": "Fase II",
                "affidabilita_stratigrafica": "media",
                "data_rilevamento": date(2023, 10, 16),
                "responsabile_compilazione": "Anna Bianchi",
                "descrizione": "Esempio di unità stratigrafica negativa.",
                "interpretazione": "Taglio di fondazione"
            }
        ]

        # Data for USM
        usm_data = [
            {
                "usm_code": "USM2001",
                "definizione": "Muro in opera incerta",
                "localita": "Ambiente 3",
                "area_struttura": "Ala Est",
                "tecnica_costruttiva": "Opus Incertum",
                "periodo": "Medievale",
                "fase": "Fase 3",
                "affidabilita_stratigrafica": "alta",
                "data_rilevamento": date(2023, 10, 18),
                "responsabile_compilazione": "Luigi Verdi",
                "descrizione": "Esempio di USM in opera incerta.",
                "orientamento": "N-S",
                "stato_conservazione": "Buono"
            },
            {
                "usm_code": "USM2002",
                "definizione": "Paramento in laterizio",
                "localita": "Prospetto Nord",
                "area_struttura": "Facciata",
                "tecnica_costruttiva": "Laterizio",
                "periodo": "Rinascimentale",
                "fase": "Fase 4",
                "affidabilita_stratigrafica": "media",
                "data_rilevamento": date(2023, 10, 20),
                "responsabile_compilazione": "Elena Neri",
                "descrizione": "Esempio di USM in laterizio.",
                "orientamento": "E-W"
            }
        ]

        # Insert US
        for data in us_data:
            stmt = select(UnitaStratigrafica).where(
                UnitaStratigrafica.site_id == site_id, 
                UnitaStratigrafica.us_code == data["us_code"]
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
                existing.updated_by = user_id
                print(f"Updated US {data['us_code']}")
            else:
                us = UnitaStratigrafica(site_id=site_id, created_by=user_id, **data)
                session.add(us)
                print(f"Added US {data['us_code']}")

        # Insert USM
        for data in usm_data:
            stmt = select(UnitaStratigraficaMuraria).where(
                UnitaStratigraficaMuraria.site_id == site_id, 
                UnitaStratigraficaMuraria.usm_code == data["usm_code"]
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
                existing.updated_by = user_id
                print(f"Updated USM {data['usm_code']}")
            else:
                usm = UnitaStratigraficaMuraria(site_id=site_id, created_by=user_id, **data)
                session.add(usm)
                print(f"Added USM {data['usm_code']}")

        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(insert_examples())
