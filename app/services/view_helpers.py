# app/services/view_helpers.py
"""
Funzioni Helper Unificate per View Routes
Modulo centralizzato per eliminare duplicazioni nei template view routes.

Fornisce funzioni comuni per:
- Gestione utente e profilo
- Verifica accesso siti
- Caricamento dati con validazione
- Preparazione context template
- Normalizzazione UUID
- Statistiche sito
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from loguru import logger

# Import modelli del sistema
from app.models import User, UserSitePermission, Photo, Document, UserActivity
from app.models.sites import ArchaeologicalSite
from app.models.user_profiles import UserProfile
from app.models.giornale_cantiere import GiornaleCantiere
from app.models.archeologia_avanzata import UnitaStratigraficaCompleta
from app.models.archaeological_records import SchedaTomba, InventarioReperto, CampioneScientifico
from app.models.form_schemas import FormSchema


# ============================================================================
# FUNZIONI HELPER PER UTENTI
# ============================================================================

async def get_current_user_with_profile(
    current_user_id: UUID, 
    db: AsyncSession,
    load_profile: bool = True
) -> User:
    """
    Recupera informazioni utente corrente con profilo opzionale.
    
    Args:
        current_user_id: UUID dell'utente corrente
        db: Sessione database asincrona
        load_profile: Se True, carica anche il profilo utente
        
    Returns:
        User: Oggetto utente con profilo caricato se richiesto
    """
    try:
        # Handle both UUID formats for consistency
        user_id_str = str(current_user_id)
        user_id_no_dashes = user_id_str.replace('-', '')
        
        # Prepara query con o senza profilo
        if load_profile:
            user_query = select(User).options(selectinload(User.profile)).where(
                (User.id == user_id_str) | (User.id == user_id_no_dashes)
            )
        else:
            user_query = select(User).where(
                (User.id == user_id_str) | (User.id == user_id_no_dashes)
            )
        
        user_result = await db.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User {current_user_id} not found in database")
            
        return user
        
    except Exception as e:
        logger.error(f"Error retrieving user {current_user_id}: {str(e)}")
        return None


async def prepare_user_context(
    current_user_id: UUID,
    db: AsyncSession,
    user_sites: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Prepara il context base per l'utente nei template.
    
    Args:
        current_user_id: UUID dell'utente corrente
        db: Sessione database
        user_sites: Lista siti accessibili dall'utente
        
    Returns:
        Dict: Context utente per template
    """
    current_user = await get_current_user_with_profile(current_user_id, db)
    
    return {
        "current_user_id": current_user_id,
        "current_user": current_user,
        "user_email": current_user.email if current_user else None,
        "user_name": current_user.full_name if current_user and hasattr(current_user, 'full_name') else current_user.email if current_user else "User",
        "user_type": "superuser" if current_user and current_user.is_superuser else "user",
        "is_superuser": current_user.is_superuser if current_user else False,
        "sites": user_sites,
        "sites_count": len(user_sites)
    }


# ============================================================================
# VERIFICA ACCESSO SITI
# ============================================================================

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verifica accesso utente al sito e restituisce informazioni sul sito.
    
    Args:
        site_id: UUID del sito
        user_sites: Lista siti accessibili dall'utente
        
    Returns:
        Dict: Informazioni sul sito
        
    Raises:
        HTTPException: Se l'accesso è negato
    """
    # Handle both hyphenated and non-hyphenated UUID formats for compatibility
    site_id_str = str(site_id)
    site_info = next(
        (site for site in user_sites if
         site["id"] == site_id_str or
         site["id"].replace("-", "") == site_id_str.replace("-", "")
        ),
        None
    )
    
    if not site_info:
        logger.error(f"Site access failed - site_id: {site_id} (type: {type(site_id)})")
        logger.error(f"Available site IDs: {[site['id'] for site in user_sites]}")
        logger.error(f"Total user sites: {len(user_sites)}")
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accesso negato al sito {site_id}"
        )
    
    return site_info


async def get_site_with_verification(
    site_id: UUID, 
    db: AsyncSession, 
    user_sites: List[Dict[str, Any]]
) -> ArchaeologicalSite:
    """
    Ottieni sito con verifica accesso.
    
    Args:
        site_id: UUID del sito
        db: Sessione database
        user_sites: Lista siti accessibili dall'utente
        
    Returns:
        ArchaeologicalSite: Oggetto sito
        
    Raises:
        HTTPException: Se l'accesso è negato o il sito non esiste
    """
    # Verifica accesso
    if not verify_site_access(site_id, user_sites):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accesso negato al sito {site_id}"
        )
    
    # Carica sito dal database
    result = await db.execute(
        select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
    )
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito {site_id} non trovato"
        )
    
    return site


# ============================================================================
# NORMALIZZAZIONE UUID
# ============================================================================

def normalize_site_id(site_id: str) -> Optional[str]:
    """
    Normalizza l'ID del sito per supportare diversi formati.
    
    Supporta:
    - UUID standard con trattini: eb8d88e1-74e3-46d3-8e86-81f926c01cab
    - Hash esadecimali senza trattini: eeedd3ceda34bf3b47d749a971b22ba
    
    Args:
        site_id: ID del sito da normalizzare
        
    Returns:
        str: L'ID normalizzato o None se non valido
    """
    if not site_id:
        return None
    
    # Rimuovi spazi bianchi
    site_id = site_id.strip()
    
    # Se è un UUID standard con trattini, valida e restituiscilo
    if '-' in site_id:
        try:
            # Crea un oggetto UUID per validare il formato
            uuid_obj = UUID(site_id)
            # Restituisci la stringa originale (già nel formato corretto)
            return site_id
        except (ValueError, AttributeError):
            return None
    
    # Se è un hash esadecimale senza trattini
    if len(site_id) == 32:
        try:
            # Verifica che sia esadecimale
            int(site_id, 16)
            # Converti in formato UUID standard (inserisci trattini)
            uuid_formatted = f"{site_id[0:8]}-{site_id[8:12]}-{site_id[12:16]}-{site_id[16:20]}-{site_id[20:32]}"
            # Valida il formato UUID risultante
            UUID(uuid_formatted)
            return uuid_formatted
        except (ValueError, AttributeError):
            return None
    
    # Altri formati non supportati
    return None


# ============================================================================
# PREPARAZIONE CONTEXT TEMPLATE
# ============================================================================

async def get_base_template_context(
    request,
    current_user_id: UUID,
    user_sites: List[Dict[str, Any]],
    db: AsyncSession,
    site: Optional[ArchaeologicalSite] = None,
    permission: Optional[UserSitePermission] = None,
    current_page: str = "dashboard"
) -> Dict[str, Any]:
    """
    Crea il context base per tutti i template.
    
    Args:
        request: Request FastAPI
        current_user_id: UUID utente corrente
        user_sites: Lista siti accessibili
        db: Sessione database
        site: Sito corrente (opzionale)
        permission: Permessi utente (opzionale)
        current_page: Pagina corrente
        
    Returns:
        Dict: Context completo per template
    """
    # Context utente base
    user_context = await prepare_user_context(current_user_id, db, user_sites)
    
    # Permessi
    can_read = permission.can_read() if permission else False
    can_write = permission.can_write() if permission else False
    can_admin = permission.can_admin() if permission else False
    
    # Context completo
    context = {
        "request": request,
        **user_context,
        "site": site,
        "user_permission": permission,
        "can_read": can_read,
        "can_write": can_write,
        "can_admin": can_admin,
        "current_page": current_page,
        "current_site_name": site.name if site else user_context.get("sites", [{}])[0].get("name", "Dashboard"),
        "first_site": user_sites[0] if user_sites else None
    }
    
    return context


# ============================================================================
# STATISTICHE SITO
# ============================================================================

async def get_site_statistics(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """
    Calcola statistiche complete del sito.
    
    Args:
        db: Sessione database
        site_id: UUID del sito
        
    Returns:
        Dict: Statistiche del sito
    """
    try:
        # Conta foto
        photos_count = await db.execute(
            select(func.count(Photo.id)).where(Photo.site_id == str(site_id))
        )
        photos_count = photos_count.scalar() or 0

        # Conta giornali di cantiere
        giornali_totali_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(GiornaleCantiere.site_id == str(site_id))
        )
        giornali_totali = giornali_totali_result.scalar() or 0

        # Conta giornali validati
        giornali_validati_result = await db.execute(
            select(func.count(GiornaleCantiere.id)).where(
                and_(
                    GiornaleCantiere.site_id == str(site_id),
                    GiornaleCantiere.validato.is_(True)
                )
            )
        )
        giornali_validati = giornali_validati_result.scalar() or 0

        # Conta utenti autorizzati
        users_count = await db.execute(
            select(func.count(UserSitePermission.id)).where(
                and_(
                    UserSitePermission.site_id == str(site_id),
                    UserSitePermission.is_active == True
                )
            )
        )
        users_count = users_count.scalar() or 0

        # Foto caricate nell'ultimo mese
        last_month = datetime.now() - timedelta(days=30)
        recent_photos = await db.execute(
            select(func.count(Photo.id)).where(
                and_(
                    Photo.site_id == str(site_id),
                    Photo.created_at >= last_month
                )
            )
        )
        recent_photos = recent_photos.scalar() or 0

        # Storage utilizzato (MB)
        storage_query = await db.execute(
            select(func.sum(Photo.file_size)).where(Photo.site_id == str(site_id))
        )
        storage_mb = (storage_query.scalar() or 0) / (1024 * 1024)

        # Conta documenti
        documents_count = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.site_id == str(site_id),
                    Document.is_deleted == False
                )
            )
        )
        documents_count = documents_count.scalar() or 0

        # Conta US/USM (Unità Stratigrafiche e Unità Stratigrafiche Murarie)
        us_count = await db.execute(
            select(func.count(UnitaStratigrafica.id)).where(UnitaStratigrafica.site_id == str(site_id))
        )
        us_count = us_count.scalar() or 0
        
        usm_count = await db.execute(
            select(func.count(UnitaStratigraficaMuraria.id)).where(UnitaStratigraficaMuraria.site_id == str(site_id))
        )
        usm_count = usm_count.scalar() or 0
        
        us_usm_count = us_count + usm_count

        return {
            "photos_count": photos_count,
            "documents_count": documents_count,
            "us_usm_count": us_usm_count,
            "us_count": us_count,
            "usm_count": usm_count,
            "giornali_totali": giornali_totali,
            "giornali_validati": giornali_validati,
            "giornali_pendenti": giornali_totali - giornali_validati,
            "users_count": users_count,
            "recent_photos": recent_photos,
            "storage_mb": round(storage_mb, 2),
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating site statistics for {site_id}: {str(e)}")
        return {
            "photos_count": 0,
            "documents_count": 0,
            "us_usm_count": 0,
            "us_count": 0,
            "usm_count": 0,
            "giornali_totali": 0,
            "giornali_validati": 0,
            "giornali_pendenti": 0,
            "users_count": 0,
            "recent_photos": 0,
            "storage_mb": 0,
            "last_updated": datetime.now().isoformat()
        }


# ============================================================================
# FUNZIONI HELPER PER ADMIN
# ============================================================================

async def require_superuser(
    request,
    current_user_id: UUID,
    user_sites: List[Dict[str, Any]],
    db: AsyncSession
) -> Tuple[User, Dict[str, Any]]:
    """
    Verifica che l'utente sia superuser e ritorna context.
    
    Args:
        request: Request FastAPI
        current_user_id: UUID utente corrente
        user_sites: Lista siti accessibili
        db: Sessione database
        
    Returns:
        Tuple[User, Dict]: Utente e context per template
        
    Raises:
        HTTPException: Se l'utente non è superuser
    """
    # Handle both UUID formats and ensure fresh data
    user_id_str = str(current_user_id)
    user_id_no_dashes = user_id_str.replace('-', '')
    
    logger.info(f"🐛 [DEBUG] require_superuser - Checking user {current_user_id}")
    logger.info(f"🐛 [DEBUG] UUID formats to try: {user_id_str} (with dashes), {user_id_no_dashes} (without dashes)")
    
    # Try with both UUID formats to ensure we find the user
    user_query = select(User).options(selectinload(User.profile)).where(
        (User.id == user_id_str) | (User.id == user_id_no_dashes)
    )
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    
    logger.info(f"🐛 [DEBUG] User found in require_superuser: {user is not None}")
    if user:
        logger.info(f"🐛 [DEBUG] User details in require_superuser - email: {user.email}, is_active: {user.is_active}, is_superuser: {user.is_superuser}")
    else:
        logger.error(f"🐛 [DEBUG] User {current_user_id} not found in require_superuser!")

    if not user or not user.is_superuser:
        logger.warning(
            f"Access denied for user {current_user_id}: "
            f"is_superuser={user.is_superuser if user else False}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso negato: solo i superadmin possono accedere a questa sezione"
        )

    # Context admin
    admin_site = {
        "id": "admin",
        "name": "Pannello Amministrazione",
        "location": "Sistema",
        "permission_level": "admin",
        "is_active": True
    }

    context = {
        "request": request,
        "sites": user_sites or [],
        "sites_count": len(user_sites) if user_sites else 0,
        "user_email": user.email if user else "Unknown",
        "user_name": user.full_name if user and hasattr(user, 'full_name') else user.email if user else "Admin",
        "user_type": "superuser" if user and user.is_superuser else "user",
        "is_superuser": user.is_superuser if user else False,
        "current_site_name": user_sites[0]["name"] if user_sites else "Amministrazione",
        "current_page": request.url.path.split("/")[-1] or "admin",
        "site": admin_site,
        "first_site": user_sites[0] if user_sites else admin_site,
        "current_user": user
    }

    logger.debug(f"Superuser {user.email} accessing admin area")
    return user, context


# ============================================================================
# FUNZIONI HELPER PER FORM SCHEMAS
# ============================================================================

async def get_form_schemas_safe(db: AsyncSession, site_id: UUID) -> List[Dict[str, Any]]:
    """
    Recupera form schemas con gestione errori centralizzata.
    
    Args:
        db: Sessione database
        site_id: UUID del sito
        
    Returns:
        List[Dict]: Lista form schemas sicura
    """
    try:
        import json

        form_schemas_query = select(FormSchema).where(
            and_(FormSchema.site_id == str(site_id), FormSchema.is_active == True)
        ).order_by(FormSchema.created_at.desc())

        form_schemas = await db.execute(form_schemas_query)
        form_schemas = form_schemas.scalars().all()

        schemas_list = []
        for schema in form_schemas:
            try:
                schema_json = json.loads(schema.schema_json)
                schemas_list.append({
                    "id": str(schema.id),
                    "name": schema.name,
                    "description": schema.description,
                    "category": schema.category,
                    "created_at": schema.created_at.isoformat(),
                    "updated_at": schema.updated_at.isoformat(),
                    "schemas": schema_json
                })
            except json.JSONDecodeError:
                continue

        return schemas_list

    except Exception as e:
        logger.error(f"Error retrieving form schemas for {site_id}: {str(e)}")
        return []


# ============================================================================
# FUNZIONI HELPER PER ATTIVITÀ RECENTI
# ============================================================================

async def get_recent_activities(db: AsyncSession, site_id: UUID, limit: int = 10) -> List[Dict]:
    """
    Recupera attività recenti del sito.
    
    Args:
        db: Sessione database
        site_id: UUID del sito
        limit: Numero massimo di attività
        
    Returns:
        List[Dict]: Lista attività recenti
    """
    try:
        activities_query = (
            select(UserActivity, User)
            .outerjoin(User, UserActivity.user_id == User.id)
            .options(selectinload(User.profile))
            .where(UserActivity.site_id == str(site_id))
            .order_by(UserActivity.activity_date.desc())
            .limit(limit)
        )

        activities_result = await db.execute(activities_query)
        activities = activities_result.all()

        return [
            {
                "id": str(activity.id),
                "type": activity.activity_type,
                "description": activity.activity_desc,
                "user": user.email if user else "Sistema",
                "date": activity.activity_date.isoformat(),
                "metadata": activity.get_extra_data() if hasattr(activity, 'get_extra_data') else {}
            }
            for activity, user in activities
        ]
        
    except Exception as e:
        logger.error(f"Error retrieving recent activities for {site_id}: {str(e)}")
        return []


# ============================================================================
# FUNZIONI HELPER PER TEAM
# ============================================================================

async def get_team_members(db: AsyncSession, site_id: UUID, limit: int = 10) -> List[Dict]:
    """
    Recupera membri del team del sito.
    
    Args:
        db: Sessione database
        site_id: UUID del sito
        limit: Numero massimo di membri
        
    Returns:
        List[Dict]: Lista membri del team
    """
    try:
        team_query = (
            select(User, UserSitePermission)
            .join(UserSitePermission, User.id == UserSitePermission.user_id)
            .options(selectinload(User.profile))
            .where(
                and_(
                    UserSitePermission.site_id == str(site_id),
                    UserSitePermission.is_active == True
                )
            )
            .order_by(UserSitePermission.permission_level.desc())
            .limit(limit)
        )

        team = await db.execute(team_query)
        team = team.all()

        return [
            {
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "permission_level": permission.permission_level,
                "permission_display": permission.permission_level.replace('_', ' ').title(),
                "granted_at": permission.created_at.isoformat()
            }
            for user, permission in team
        ]
        
    except Exception as e:
        logger.error(f"Error retrieving team members for {site_id}: {str(e)}")
        return []


# ============================================================================
# FUNZIONI HELPER PER FOTO RECENTI
# ============================================================================

async def get_recent_photos(db: AsyncSession, site_id: UUID, limit: int = 6) -> List[Dict]:
    """
    Recupera foto recenti del sito.
    
    Args:
        db: Sessione database
        site_id: UUID del sito
        limit: Numero massimo di foto
        
    Returns:
        List[Dict]: Lista foto recenti
    """
    try:
        photos_query = select(Photo).where(
            Photo.site_id == str(site_id)
        ).order_by(Photo.created_at.desc()).limit(limit)

        photos = await db.execute(photos_query)
        photos = photos.scalars().all()

        return [
            {
                "id": str(photo.id),
                "filename": photo.filename,
                "thumbnail_url": f"/photos/{photo.id}/thumbnail",
                "full_url": f"/photos/{photo.id}/full",
                "photo_type": photo.photo_type if photo.photo_type else None,
                "created_at": photo.created_at.isoformat(),
                "category": getattr(photo, 'category', None)
            }
            for photo in photos
        ]
        
    except Exception as e:
        logger.error(f"Error retrieving recent photos for {site_id}: {str(e)}")
        return []