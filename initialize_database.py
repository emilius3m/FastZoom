#!/usr/bin/env python3
"""
Script di inizializzazione del database per FastZoom
Crea siti archeologici di esempio e un utente amministratore
"""

import asyncio
import sys
import os
from uuid import uuid4
from datetime import datetime

# Aggiungi la directory del progetto al path Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Import dei modelli necessari
from app.models.sites import ArchaeologicalSite, SiteStatusEnum, SiteTypeEnum, ResearchStatusEnum
from app.models.users import User, UserStatusEnum, UserSitePermission, PermissionLevel
from app.database.session import AsyncSessionLocal
from app.database.security import SecurityService
from app.services.site_service import SiteService
from app.services.permissions_service import PermissionsService


async def create_database_session() -> AsyncSession:
    """Crea una sessione del database"""
    async with AsyncSessionLocal() as session:
        return session


async def check_existing_sites(session: AsyncSession) -> bool:
    """Verifica se i siti esistono già nel database"""
    print("Verifica dell'esistenza dei siti archeologici...")
    
    # Controlla SITE001
    result = await session.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.code == "SITE001")
    )
    site1 = result.scalar_one_or_none()
    
    # Controlla SITE002
    result = await session.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.code == "SITE002")
    )
    site2 = result.scalar_one_or_none()
    
    if site1 and site2:
        print("OK Entrambi i siti archeologici esistono già")
        return True
    elif site1 or site2:
        print("! Solo uno dei siti esiste già. Procederò con la creazione del sito mancante.")
        return False
    else:
        print("X Nessun sito archeologico trovato. Procedero con la creazione.")
        return False


async def check_existing_user(session: AsyncSession) -> bool:
    """Verifica se l'utente esiste già nel database"""
    print("Verifica dell'esistenza dell'utente...")
    
    result = await session.execute(
        select(User).where(User.email == "user@user.com")
    )
    user = result.scalar_one_or_none()
    
    if user:
        print(f"OK Utente {user.email} esiste già")
        return True
    else:
        print("X Utente non trovato. Procedero con la creazione.")
        return False


async def create_archaeological_sites(session: AsyncSession, user_id=None):
    """Crea i siti archeologici di esempio"""
    print("\n=== Creazione Siti Archeologici ===")
    
    # Dati per i siti
    sites_data = [
        {
            "name": "Sito Archeologico A",
            "code": "SITE001",
            "site_type": SiteTypeEnum.ABITATO,
            "status": SiteStatusEnum.ACTIVE,
            "research_status": ResearchStatusEnum.EXCAVATION,
            "country": "Italia",
            "region": "Lazio",
            "municipality": "Roma",
            "description": "Sito archeologico di esempio A per test del sistema FastZoom"
        },
        {
            "name": "Sito Archeologico B",
            "code": "SITE002",
            "site_type": SiteTypeEnum.NECROPOLI,
            "status": SiteStatusEnum.ACTIVE,
            "research_status": ResearchStatusEnum.SURVEY,
            "country": "Italia",
            "region": "Toscana",
            "municipality": "Firenze",
            "description": "Sito archeologico di esempio B per test del sistema FastZoom"
        }
    ]
    
    created_sites = []
    
    for site_data in sites_data:
        # Verifica se il sito esiste già
        result = await session.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.code == site_data["code"])
        )
        existing_site = result.scalar_one_or_none()
        
        if existing_site:
            print(f"OK Sito {site_data['code']} ({site_data['name']}) esiste già")
            created_sites.append(existing_site)
        else:
            # Crea nuovo sito
            new_site = ArchaeologicalSite(
                id=uuid4(),
                created_by=user_id,
                **site_data
            )
            
            session.add(new_site)
            await session.commit()
            await session.refresh(new_site)
            
            print(f"OK Creato sito {new_site.code} ({new_site.name})")
            created_sites.append(new_site)
    
    return created_sites


async def create_user(session: AsyncSession):
    """Crea l'utente di esempio"""
    print("\n=== Creazione Utente ===")
    
    # Verifica se l'utente esiste già
    result = await session.execute(
        select(User).where(User.email == "user@user.com")
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        print(f"OK Utente {existing_user.email} esiste già")
        return existing_user
    
    # Hash della password
    password = "user@user.com"
    hashed_password = SecurityService.get_password_hash(password)
    
    # Crea nuovo utente
    new_user = User(
        id=uuid4(),
        email="user@user.com",
        username="user",
        hashed_password=hashed_password,
        first_name="User",
        last_name="Test",
        status=UserStatusEnum.ACTIVE,
        is_active=True,
        is_verified=True,
        is_superuser=False
    )
    
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    
    print(f"OK Creato utente {new_user.email} con password '{password}'")
    return new_user


async def assign_admin_permissions(session: AsyncSession, user: User, sites: list):
    """Assegna permessi di amministratore all'utente per tutti i siti"""
    print("\n=== Assegnazione Permessi di Amministratore ===")
    
    for site in sites:
        # Verifica se il permesso esiste già
        result = await session.execute(
            select(UserSitePermission).where(
                UserSitePermission.user_id == user.id,
                UserSitePermission.site_id == site.id
            )
        )
        existing_permission = result.scalar_one_or_none()
        
        if existing_permission:
            if existing_permission.permission_level == PermissionLevel.ADMIN:
                print(f"OK L'utente {user.email} ha già permessi di admin per il sito {site.code}")
            else:
                # Aggiorna il permesso esistente ad admin
                existing_permission.permission_level = PermissionLevel.ADMIN
                existing_permission.updated_at = datetime.utcnow()
                await session.commit()
                print(f"OK Aggiornato permesso a admin per l'utente {user.email} sul sito {site.code}")
        else:
            # Crea nuovo permesso di amministratore
            new_permission = UserSitePermission(
                id=uuid4(),
                user_id=user.id,
                site_id=site.id,
                permission_level=PermissionLevel.ADMIN,
                permissions=["read", "write", "delete", "export", "admin", "upload", "validate", "publish"],
                site_role="director",
                is_active=True,
                granted_by=user.id,  # Auto-assegnato
                granted_at=datetime.utcnow()
            )
            
            session.add(new_permission)
            await session.commit()
            print(f"OK Assegnato permesso di admin per l'utente {user.email} sul sito {site.code}")


async def main():
    """Funzione principale dello script"""
    print("=== Inizializzazione Database FastZoom ===")
    print("Questo script creerà dati di esempio per il sistema FastZoom\n")
    
    # Crea sessione del database
    async with AsyncSessionLocal() as session:
        try:
            # Verifica esistenza dei dati
            sites_exist = await check_existing_sites(session)
            user_exists = await check_existing_user(session)
            
            if sites_exist and user_exists:
                print("\nOK Tutti i dati esistono già. Nessuna azione richiesta.")
                return
            
            # Crea utente prima dei siti
            user = await create_user(session)
            
            # Crea siti archeologici passando l'ID dell'utente
            sites = await create_archaeological_sites(session, user.id)
            
            # Assegna permessi di amministratore
            await assign_admin_permissions(session, user, sites)
            
            print("\n=== Riepilogo ===")
            print(f"OK Creati/verificati {len(sites)} siti archeologici:")
            for site in sites:
                print(f"  - {site.code}: {site.name} ({site.municipality}, {site.region})")
            
            print(f"OK Creato/verificato utente: {user.email}")
            print(f"OK Assegnati permessi di amministratore per tutti i siti")
            
            print("\n=== Informazioni di Accesso ===")
            print(f"Email: user@user.com")
            print(f"Password: user@user.com")
            print(f"Username: user")
            print("\nL'utente ha permessi di amministratore per entrambi i siti.")
            
        except Exception as e:
            print(f"\nERRORE durante l'inizializzazione: {str(e)}")
            import traceback
            traceback.print_exc()
            await session.rollback()
            sys.exit(1)


if __name__ == "__main__":
    # Esegui la funzione principale
    asyncio.run(main())