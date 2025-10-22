#!/usr/bin/env python3
"""
Script di verifica per il database FastZoom
Verifica che i dati siano stati creati correttamente
"""

import asyncio
import sys
import os

# Aggiungi la directory del progetto al path Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Import dei modelli necessari
from app.models.sites import ArchaeologicalSite
from app.models.users import User, UserSitePermission, PermissionLevel
from app.database.session import AsyncSessionLocal


async def verify_sites(session: AsyncSession):
    """Verifica i siti archeologici"""
    print("=== Verifica Siti Archeologici ===")
    
    # Conta tutti i siti
    result = await session.execute(select(ArchaeologicalSite))
    sites = result.scalars().all()
    
    print(f"Numero totale di siti nel database: {len(sites)}")
    
    for site in sites:
        print(f"- {site.code}: {site.name} ({site.municipality}, {site.region})")
        print(f"  Tipo: {site.site_type}, Stato: {site.status}, Ricerca: {site.research_status}")
        print(f"  Creato da: {site.created_by}")
    
    # Verifica siti specifici
    site001 = await session.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.code == "SITE001")
    )
    site001 = site001.scalar_one_or_none()
    
    site002 = await session.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.code == "SITE002")
    )
    site002 = site002.scalar_one_or_none()
    
    if site001 and site002:
        print("OK Entrambi i siti attesi sono presenti nel database")
        return True
    else:
        print("ERRORE Mancano uno o entrambi i siti attesi")
        return False


async def verify_user(session: AsyncSession):
    """Verifica l'utente"""
    print("\n=== Verifica Utente ===")
    
    # Cerca l'utente
    result = await session.execute(
        select(User).where(User.email == "user@user.com")
    )
    user = result.scalar_one_or_none()
    
    if user:
        print(f"OK Utente trovato: {user.email}")
        print(f"  Nome: {user.first_name} {user.last_name}")
        print(f"  Username: {user.username}")
        print(f"  Status: {user.status}")
        print(f"  Attivo: {user.is_active}")
        print(f"  Verificato: {user.is_verified}")
        return user
    else:
        print("ERRORE Utente non trovato")
        return None


async def verify_permissions(session: AsyncSession, user: User):
    """Verifica i permessi utente"""
    print("\n=== Verifica Permessi ===")
    
    # Cerca i permessi dell'utente
    result = await session.execute(
        select(UserSitePermission).where(UserSitePermission.user_id == user.id)
    )
    permissions = result.scalars().all()
    
    print(f"Numero di permessi per l'utente: {len(permissions)}")
    
    sites_with_admin = []
    for perm in permissions:
        # Carica il sito correlato
        site_result = await session.execute(
            select(ArchaeologicalSite).where(ArchaeologicalSite.id == perm.site_id)
        )
        site = site_result.scalar_one_or_none()
        
        if site:
            print(f"- Sito {site.code}: {perm.permission_level} ({perm.permission_display_name})")
            if perm.permission_level == PermissionLevel.ADMIN.value:
                sites_with_admin.append(site.code)
    
    # Verifica che l'utente abbia permessi di admin per entrambi i siti
    if "SITE001" in sites_with_admin and "SITE002" in sites_with_admin:
        print("OK L'utente ha permessi di amministratore per entrambi i siti")
        return True
    else:
        print(f"ERRORE L'utente non ha permessi di admin per tutti i siti. Admin per: {sites_with_admin}")
        return False


async def main():
    """Funzione principale"""
    print("=== Verifica Database FastZoom ===\n")
    
    async with AsyncSessionLocal() as session:
        try:
            # Verifica siti
            sites_ok = await verify_sites(session)
            
            # Verifica utente
            user = await verify_user(session)
            
            # Verifica permessi
            if user:
                permissions_ok = await verify_permissions(session, user)
            else:
                permissions_ok = False
            
            # Riepilogo
            print("\n=== Riepilogo Verifica ===")
            if sites_ok and user and permissions_ok:
                print("OK Tutti i verifiche superate con successo!")
                print("OK Database inizializzato correttamente")
                return True
            else:
                print("ERRORE Alcune verifiche sono fallite")
                if not sites_ok:
                    print("- Siti archeologici mancanti o incompleti")
                if not user:
                    print("- Utente mancante")
                if not permissions_ok:
                    print("- Permessi mancanti o errati")
                return False
                
        except Exception as e:
            print(f"\nERRORE Errore durante la verifica: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)