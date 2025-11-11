# app/routes/api/dependencies.py - Shared dependencies for API routes

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from uuid import UUID

from app.database.session import get_async_session
from app.core.security import get_current_user_id_with_blacklist
from app.models import ArchaeologicalSite
from app.models import UserSitePermission


async def get_site_access(
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito e restituisce sito e permessi"""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == str(current_user_id),
            UserSitePermission.site_id == str(site_id),
            UserSitePermission.is_active == True,
            or_(
                UserSitePermission.expires_at.is_(None),
                UserSitePermission.expires_at > func.now()
            )
        )
    )

    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()

    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )

    return site, permission


async def get_photo_site_access(
        photo_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito della foto e restituisce sito e permessi"""
    
    # Import Photo model here to avoid circular imports
    from app.models.documentation_and_field import Photo
    
    # Verifica esistenza foto
    photo_query = select(Photo).where(Photo.id == photo_id)
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    
    # Usa la funzione esistente per verificare l'accesso al sito della foto
    return await get_site_access(photo.site_id, current_user_id, db)