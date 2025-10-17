#!/usr/bin/env python3
"""
Test script per verificare il salvataggio delle schede ICCD
"""

import asyncio
import sys
import os

# Aggiungi il path del progetto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_async_session
from app.models.iccd_records import ICCDRecord
from app.models.sites import ArchaeologicalSite
from app.models import User
from sqlalchemy import select, func
from uuid import uuid4


async def test_iccd_saving():
    """Test per verificare se il salvataggio ICCD funziona."""

    print("🔍 Test salvataggio schede ICCD...")

    try:
        async with get_async_session() as db:
            # Verifica se esistono tabelle ICCD
            try:
                # Test query semplice
                count_query = select(func.count(ICCDRecord.id))
                total = await db.execute(count_query)
                total = total.scalar()
                print(f"✅ Trovate {total} schede ICCD esistenti nel database")

            except Exception as e:
                print(f"❌ Errore accesso tabella ICCD: {e}")
                print("   Possibile problema: le tabelle ICCD non esistono o la migrazione non è stata eseguita")
                return False

            # Verifica se esistono siti archeologici
            try:
                sites_query = select(ArchaeologicalSite).limit(1)
                sites = await db.execute(sites_query)
                sites = sites.scalars().all()

                if not sites:
                    print("⚠️  Nessun sito archeologico trovato")
                    print("   Suggerimento: crea prima un sito archeologico")
                    return False

                site = sites[0]
                print(f"✅ Utilizzando sito: {site.name} (ID: {site.id})")

            except Exception as e:
                print(f"❌ Errore accesso tabella siti: {e}")
                return False

            # Verifica se esistono utenti
            try:
                users_query = select(User).limit(1)
                users = await db.execute(users_query)
                users = users.scalars().all()

                if not users:
                    print("⚠️  Nessun utente trovato")
                    print("   Suggerimento: crea prima un utente")
                    return False

                user = users[0]
                print(f"✅ Utilizzando utente: {user.email} (ID: {user.id})")

            except Exception as e:
                print(f"❌ Errore accesso tabella utenti: {e}")
                return False

            # Test creazione record ICCD
            print("\n📝 Test creazione nuova scheda ICCD...")

            test_data = {
                'schema_type': 'RA',
                'level': 'C',
                'cataloging_institution': 'SSABAP-RM',
                'iccd_data': {
                    'CD': {
                        'TSK': 'RA',
                        'LIR': 'C',
                        'NCT': {
                            'NCTR': '12',
                            'NCTN': f"TEST{uuid4().hex[:6].upper()}",
                            'NCTS': None
                        },
                        'ESC': 'SSABAP-RM'
                    },
                    'OG': {
                        'OGT': {
                            'OGTD': 'Test Object',
                            'OGTT': 'Test Type'
                        }
                    },
                    'LC': {
                        'PVC': {
                            'PVCS': 'Italia',
                            'PVCR': 'Lazio',
                            'PVCP': 'RM',
                            'PVCC': 'Roma'
                        }
                    },
                    'DT': {
                        'DTS': {
                            'DTSI': 'I d.C.',
                            'DTSF': 'II d.C.'
                        }
                    },
                    'MT': {
                        'MTC': {
                            'MTCM': ['ceramica']
                        }
                    },
                    'DA': {
                        'DES': {
                            'DESO': 'Test description for ICCD record'
                        },
                        'STC': {
                            'STCC': 'buono'
                        }
                    }
                }
            }

            try:
                # Crea record
                iccd_record = ICCDRecord(
                    nct_region=test_data['iccd_data']['CD']['NCT']['NCTR'],
                    nct_number=test_data['iccd_data']['CD']['NCT']['NCTN'],
                    nct_suffix=test_data['iccd_data']['CD']['NCT']['NCTS'],
                    schema_type=test_data['schema_type'],
                    level=test_data['level'],
                    iccd_data=test_data['iccd_data'],
                    cataloging_institution=test_data['cataloging_institution'],
                    site_id=site.id,
                    created_by=user.id
                )

                db.add(iccd_record)
                await db.flush()
                await db.refresh(iccd_record)

                print(f"✅ Record ICCD creato con successo!")
                print(f"   ID: {iccd_record.id}")
                print(f"   NCT: {iccd_record.get_nct()}")
                print(f"   Schema: {iccd_record.schema_type}")
                print(f"   Livello: {iccd_record.level}")

                # Commit finale
                await db.commit()

                # Verifica che il record sia stato salvato
                saved_record = await db.execute(
                    select(ICCDRecord).where(ICCDRecord.id == iccd_record.id)
                )
                saved_record = saved_record.scalar_one_or_none()

                if saved_record:
                    print("✅ Record verificato nel database dopo commit")
                    return True
                else:
                    print("❌ Record non trovato dopo commit")
                    return False

            except Exception as e:
                print(f"❌ Errore creazione record: {e}")
                await db.rollback()
                return False

    except Exception as e:
        print(f"❌ Errore connessione database: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_iccd_saving())

    if result:
        print("\n🎉 Test completato con successo! Il sistema ICCD funziona correttamente.")
        sys.exit(0)
    else:
        print("\n💥 Test fallito! Ci sono problemi con il sistema ICCD.")
        sys.exit(1)