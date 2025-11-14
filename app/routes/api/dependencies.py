# app/routes/api/dependencies.py - Shared dependencies for API routes

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from uuid import UUID

from app.database.session import get_async_session
from app.core.security import get_current_user_id_with_blacklist
from app.models import ArchaeologicalSite
from app.models import UserSitePermission


def normalize_site_id(site_id_input):
    """
    Normalize site ID to handle both UUID and hex hash formats.
    
    Args:
        site_id_input: Site ID as string (UUID with dashes or hex hash without dashes)
        
    Returns:
        Normalized site_id as string in UUID format, or None if invalid
        
    Examples:
        normalize_site_id("eb8d88e1-74e3-46d3-8e86-81f926c01cab") -> "eb8d88e1-74e3-46d3-8e86-81f926c01cab"
        normalize_site_id("eeeedd3ceda34bf3b47d749a971b22ba") -> "eeeedd3c-eda3-4bf3-b47d-749a971b22ba"
        normalize_site_id("invalid-id") -> None
    """
    if not site_id_input:
        return None
    
    # Remove whitespace
    site_id_input = site_id_input.strip()
    
    # If it's already a UUID with dashes, validate and return as is
    if '-' in site_id_input:
        try:
            UUID(site_id_input)
            return site_id_input
        except ValueError:
            return None
    
    # If it's a 32-character hex hash, convert to UUID format
    if len(site_id_input) == 32:
        try:
            # Convert hex hash to UUID with dashes
            normalized = f"{site_id_input[:8]}-{site_id_input[8:12]}-{site_id_input[12:16]}-{site_id_input[16:20]}-{site_id_input[20:]}"
            UUID(normalized)  # Validate the format
            return normalized
        except ValueError:
            return None
    
    # Try to validate as UUID directly
    try:
        UUID(site_id_input)
        return site_id_input
    except ValueError:
        return None


async def get_site_access_by_id(
    site_id: UUID,
    current_user_id: UUID,
    db: AsyncSession
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """
    Get site access by UUID - helper function for cases where we already have a UUID
    """
    # Use normalized string for database queries
    normalized_site_id = str(site_id)
    
    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")
    
    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == str(current_user_id),
            UserSitePermission.site_id == normalized_site_id,
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


async def get_site_access(
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito e restituisce sito e permessi"""
    
    # Use normalized string for database queries
    normalized_site_id = str(site_id)

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == str(current_user_id),
            UserSitePermission.site_id == normalized_site_id,
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


async def get_normalized_site_id(
        site_id: str,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
) -> str:
    """
    Normalizza l'ID del sito per gestire sia UUID con trattini che hash esadecimale.
    Funzione dependency per endpoint che necessitano solo dell'ID normalizzato.
    
    Args:
        site_id: ID del sito (UUID con trattini o hash esadecimale)
        
    Returns:
        ID normalizzato in formato UUID standard
        
    Raises:
        HTTPException: Se l'ID non è valido
    """
    normalized = normalize_site_id(site_id)
    if not normalized:
        raise HTTPException(status_code=404, detail="ID sito non valido")
    
    # Verifica che il sito esista e l'utente ha accesso
    await get_site_access(UUID(normalized), current_user_id, db)
    
    return normalized


async def get_normalized_site_id_no_auth(
        site_id: str
) -> str:
    """
    Normalizza l'ID del sito senza verificare i permessi.
    Utile per endpoint interni dove i permessi sono già verificati.
    
    Args:
        site_id: ID del sito (UUID con trattini o hash esadecimale)
        
    Returns:
        ID normalizzato in formato UUID standard
        
    Raises:
        HTTPException: Se l'ID non è valido
    """
    normalized = normalize_site_id(site_id)
    if not normalized:
        raise HTTPException(status_code=404, detail="ID sito non valido")
    
    return normalized


async def get_photo_site_access(
        photo_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
        db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito della foto e restituisce sito e permessi"""
    
    # Import Photo model here to avoid circular imports
    from app.models.documentation_and_field import Photo
    
    # Verifica esistenza foto - FIX: Convert UUID to string for proper comparison
    photo_id_str = str(photo_id)
    photo_query = select(Photo).where(Photo.id == photo_id_str)
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    
    # Usa la funzione esistente per verificare l'accesso al sito della foto
    return await get_site_access(photo.site_id, current_user_id, db)