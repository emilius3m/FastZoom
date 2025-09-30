# app/routes/sites_router.py - DASHBOARD GESTIONE SITO ARCHEOLOGICO

from fastapi import APIRouter, Depends, Request, HTTPException, status, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import asyncio

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.users import User, UserActivity
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission, PermissionLevel
from app.models.photos import Photo, PhotoType, MaterialType, ConservationStatus
from app.models.form_schemas import FormSchema
from app.templates import templates
from app.services.storage_service import storage_service
from app.services.photo_service import photo_metadata_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.storage_management_service import storage_management_service

# Import API router for hierarchical ICCD system
from app.routes.api.iccd_hierarchy import iccd_hierarchy_router

sites_router = APIRouter(prefix="/sites", tags=["sites"])

# Include hierarchical ICCD API endpoints
sites_router.include_router(iccd_hierarchy_router, prefix="/{site_id}")


async def get_site_access(
        site_id: UUID,
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito e restituisce sito e permessi"""

    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")

    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == current_user_id,
            UserSitePermission.site_id == site_id,
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


@sites_router.get("/{site_id}/dashboard", response_class=HTMLResponse)
async def site_dashboard(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Dashboard principale per gestione sito archeologico"""
    site, permission = site_access

    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()

    # Statistiche del sito
    stats = await get_site_statistics(db, site_id)

    # Attività recenti
    recent_activities = await get_recent_activities(db, site_id, limit=10)

    # Foto recenti
    recent_photos = await get_recent_photos(db, site_id, limit=6)

    # Team del sito
    team_members = await get_site_team(db, site_id)

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "stats": stats,
        "recent_activities": recent_activities,
        "recent_photos": recent_photos,
        "team_members": team_members,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }

    return templates.TemplateResponse("sites/dashboard.html", context)


@sites_router.get("/{site_id}/photos", response_class=HTMLResponse)
async def site_photos(
        request: Request,
        site_id: UUID,
        page: int = 1,
        per_page: int = 24,
        category: str = None,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione collezione fotografica del sito"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Query foto con paginazione
    photos_query = select(Photo).where(Photo.site_id == site_id)

    if category:
        photos_query = photos_query.where(Photo.photo_type == category)

    # Conta totale
    total_query = select(func.count(Photo.id)).where(Photo.site_id == site_id)
    if category:
        total_query = total_query.where(Photo.photo_type == category)

    total_photos = await db.execute(total_query)
    total_photos = total_photos.scalar()

    # Foto paginate
    photos_query = photos_query.offset((page - 1) * per_page).limit(per_page)
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    # Categorie disponibili
    categories_query = select(Photo.photo_type, func.count(Photo.id)).where(
        Photo.site_id == site_id
    ).group_by(Photo.photo_type)
    categories = await db.execute(categories_query)
    categories = categories.all()

    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "user_role": permission.permission_level.value,
        "photos": [photo.to_dict() for photo in photos],
        "current_page": page,
        "per_page": per_page,
        "total_photos": total_photos,
        "total_pages": (total_photos + per_page - 1) // per_page,
        "current_photo_type": category,
        "categories": categories,
        "can_write": permission.can_write()
    }

    return templates.TemplateResponse("sites/photos.html", context)


@sites_router.get("/{site_id}/documentation", response_class=HTMLResponse)
async def site_documentation(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione documentazione e rapporti del sito"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Documenti del sito (assumendo un modello Document)
    documents = []  # TODO: Implementare get_site_documents quando disponibile il modello Document
    
    # Form schemas del sito
    form_schemas_query = select(FormSchema).where(
        and_(FormSchema.site_id == site_id, FormSchema.is_active == True)
    ).order_by(FormSchema.created_at.desc())
    
    form_schemas = await db.execute(form_schemas_query)
    form_schemas = form_schemas.scalars().all()
    
    # Prepara i form schema per il template
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
                "schema": schema_json
            })
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in schema {schema.id}")
            continue

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "documents": documents,
        "form_schemas": schemas_list,
        "can_write": permission.can_write()
    }

    return templates.TemplateResponse("sites/documentation.html", context)


@sites_router.get("/{site_id}/team", response_class=HTMLResponse)
async def site_team_management(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione team del sito (solo per admin sito)"""
    site, permission = site_access

    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Solo amministratori del sito")

    # Team completo del sito
    team_members = await get_site_team(db, site_id)

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "team_members": team_members
    }

    return templates.TemplateResponse("sites/teams.html", context)


@sites_router.get("/{site_id}/archaeological-plans", response_class=HTMLResponse)
async def site_archaeological_plans(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Gestione piante archeologiche e griglie di scavo"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }
    
    return templates.TemplateResponse("sites/archaeological_plans.html", context)


# === API ENDPOINTS PER DASHBOARD ===

@sites_router.get("/{site_id}/api/stats")
async def get_site_stats_api(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """API per statistiche del sito (per aggiornamenti real-time)"""
    site, permission = site_access
    stats = await get_site_statistics(db, site_id)
    return JSONResponse(stats)


@sites_router.get("/{site_id}/api/photos")
async def get_site_photos_api(
        site_id: UUID,
        page: int = 1,
        per_page: int = 100,
        category: str = None,
        search: str = None,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """API per ottenere lista foto del sito in formato JSON"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Query foto
    photos_query = select(Photo).where(Photo.site_id == site_id)

    if category:
        photos_query = photos_query.where(Photo.photo_type == category)

    if search:
        search_term = f"%{search}%"
        photos_query = photos_query.where(
            or_(
                Photo.filename.ilike(search_term),
                Photo.title.ilike(search_term),
                Photo.description.ilike(search_term)
            )
        )

    # Ordina per data di upload (più recenti prima)
    photos_query = photos_query.order_by(Photo.created.desc())

    # Get all photos (we'll handle pagination on frontend if needed)
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    # Convert to dictionary format with proper URLs
    photos_data = []
    for photo in photos:
        photo_dict = photo.to_dict()
        # Add proper URLs for frontend
        photo_dict['file_url'] = f"/photos/{photo.id}/full"
        photo_dict['thumbnail_url'] = f"/photos/{photo.id}/thumbnail"
        photos_data.append(photo_dict)

    return JSONResponse(photos_data)


@sites_router.post("/{site_id}/api/photos/upload")
async def upload_photo(
        site_id: UUID,
        photos: List[UploadFile] = File(...),
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        photo_type: Optional[str] = Form(None),
        photographer: Optional[str] = Form(None),
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Upload foto al sito archeologico - FIXED: Background processing non bloccante

    Args:
        site_id: ID del sito archeologico
        photos: Lista file immagini da caricare
        title: Titolo foto (opzionale)
        description: Descrizione foto (opzionale)
        photo_type: Tipo di foto archeologica (opzionale)
        photographer: Nome fotografo (opzionale)
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        uploaded_photos = []

        # Process each photo - Upload first, schedule background processing after
        for file in photos:
            try:
                # Ensure MinIO buckets exist before uploading
                await storage_management_service.ensure_buckets_exist()
                
                # 1. Check storage health before uploading
                storage_usage = await storage_management_service.get_storage_usage()
                if storage_usage.get('total_size_gb', 0) > 8:  # >80% of 10GB
                    logger.warning(f"Storage usage critical ({storage_usage.get('total_size_gb', 0)}GB), triggering cleanup")
                    cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=1000)
                    logger.info(f"Pre-upload cleanup: {cleanup_result}")

                # 2. Salva file su MinIO
                filename, file_path, file_size = await storage_service.save_upload_file(
                    file, str(site_id), str(current_user_id)
                )

                # 3. Estrai metadati dal file caricato
                await file.seek(0)  # Reset file pointer
                exif_data, metadata = await photo_metadata_service.extract_metadata_from_file(
                    file, filename
                )

                # 4. Crea record nel database
                photo_record = await photo_metadata_service.create_photo_record(
                    filename=filename,
                    original_filename=file.filename,
                    file_path=file_path,
                    file_size=file_size,
                    site_id=str(site_id),
                    uploaded_by=str(current_user_id),
                    metadata=metadata
                )

                # 5. Sovrascrivi metadati forniti dall'utente
                if title:
                    photo_record.title = title
                if description:
                    photo_record.description = description
                if photographer:
                    photo_record.photographer = photographer
                if photo_type:
                    try:
                        photo_record.photo_type = PhotoType(photo_type)
                    except ValueError:
                        logger.warning(f"Tipo foto non valido: {photo_type}")

                # 6. Salva nel database PRIMA di generare il thumbnail
                db.add(photo_record)
                await db.commit()
                await db.refresh(photo_record)

                # Log photo ID for debugging
                logger.info(f"Photo record saved with ID: {photo_record.id}")

                # 7. Genera thumbnail DOPO che il record è stato salvato
                await file.seek(0)  # Reset file pointer per thumbnail
                thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                    file, str(photo_record.id)
                )

                if thumbnail_path:
                    photo_record.thumbnail_path = thumbnail_path
                    # Salva il thumbnail path nel database
                    await db.commit()
                    logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
                else:
                    logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")

                # Log thumbnail path for debugging
                logger.info(f"Photo {photo_record.id} saved with thumbnail_path: {photo_record.thumbnail_path}")
                
            except HTTPException as he:
                # Handle HTTP exceptions (like storage full)
                if he.status_code == 507:  # Storage full
                    logger.error(f"Storage full during upload of {file.filename}")
                    # Try one more cleanup attempt
                    try:
                        cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=2000)
                        if cleanup_result['success']:
                            logger.info(f"Emergency cleanup successful: {cleanup_result['total_freed_mb']}MB freed")
                            # Could retry upload here if needed
                        else:
                            logger.error(f"Emergency cleanup failed: {cleanup_result}")
                    except Exception as cleanup_error:
                        logger.error(f"Cleanup attempt failed: {cleanup_error}")
                
                # Re-raise the HTTP exception to be handled by outer try-catch
                raise he
                
            except Exception as photo_error:
                logger.error(f"Error processing photo {file.filename}: {photo_error}")
                # Continue with other photos, don't fail the entire batch
                continue

            # 7. Log attività
            activity = UserActivity(
                user_id=current_user_id,
                site_id=site_id,
                activity_type="UPLOAD",
                activity_desc=f"Caricata foto: {file.filename}",
                extra_data=json.dumps({
                    "photo_id": str(photo_record.id),
                    "filename": filename,
                    "file_size": file_size
                })
            )

            db.add(activity)
            await db.commit()

            logger.info(f"Photo uploaded successfully: {photo_record.id} by user {current_user_id}")

            uploaded_photos.append({
                "photo_id": str(photo_record.id),
                "filename": filename,
                "file_size": file_size,
                "metadata": {
                    "width": photo_record.width,
                    "height": photo_record.height,
                    "photo_date": photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                    "camera_model": photo_record.camera_model
                }
            })

        # 8. FIXED: Schedule deep zoom processing AFTER all uploads are complete
        # This ensures uploads don't block each other
        for photo_data in uploaded_photos:
            photo_id = photo_data["photo_id"]
            try:
                # Get photo record from database
                photo_query = select(Photo).where(Photo.id == UUID(photo_id))
                result = await db.execute(photo_query)
                photo_record = result.scalar_one_or_none()
                
                if not photo_record:
                    logger.warning(f"Photo record not found for deep zoom scheduling: {photo_id}")
                    continue

                # Read file content for deep zoom check
                try:
                    # Get file from storage for processing
                    photo_content = await archaeological_minio_service.get_file(photo_record.file_path)
                    
                    from PIL import Image
                    import io
                    
                    with Image.open(io.BytesIO(photo_content)) as img:
                        width, height = img.size
                        max_dimension = max(width, height)
                        
                        # Schedule deep zoom processing only for images > 2000px
                        if max_dimension > 2000:
                            logger.info(f"Scheduling deep zoom processing for large image {photo_id}: {width}x{height}")
                            
                            # Set status to scheduled
                            photo_record.deep_zoom_status = 'scheduled'
                            await db.commit()
                            
                            # FIXED: Use the new async scheduling method for non-blocking execution
                            await deep_zoom_minio_service.schedule_tiles_generation_async(
                                photo_id=photo_id,
                                original_file_content=photo_content,
                                site_id=str(site_id),
                                archaeological_metadata={
                                    'inventory_number': photo_record.inventory_number,
                                    'excavation_area': photo_record.excavation_area,
                                    'material': photo_record.material.value if photo_record.material else None,
                                    'chronology_period': photo_record.chronology_period,
                                    'photo_type': photo_record.photo_type.value if photo_record.photo_type else None,
                                    'photographer': photo_record.photographer,
                                    'description': photo_record.description,
                                    'keywords': photo_record.keywords
                                }
                            )
                            
                            logger.info(f"✅ Deep zoom processing scheduled for photo {photo_id}")
                        else:
                            logger.info(f"Skipping deep zoom for small image {photo_id}: {width}x{height}")
                            
                except Exception as img_error:
                    logger.warning(f"Could not determine image dimensions for {photo_id}: {img_error}")

            except Exception as e:
                logger.error(f"❌ Deep zoom scheduling failed for photo {photo_id}: {e}")
                # Non bloccare l'upload se scheduling fallisce

        return JSONResponse({
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "uploaded_photos": uploaded_photos
        })

    except HTTPException:
        # Rilancia eccezioni HTTP
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        # Se file è stato salvato, prova a eliminarlo
        if 'filename' in locals():
            await storage_service.delete_file(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante upload: {str(e)}"
        )


@sites_router.get("/{site_id}/api/team")
async def get_team_members(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Get team members for a site"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    # Query corretta con JOIN per ottenere dati utente
    query = select(
        UserSitePermission,
        User.first_name,
        User.last_name,
        User.email,
        User.profile_data  # Assuming you store additional data here
    ).join(
        User, UserSitePermission.user_id == User.id
    ).where(
        UserSitePermission.site_id == site_id
    ).order_by(UserSitePermission.created_at.desc())

    result = await db.execute(query)
    team_data = result.fetchall()

    # Format response
    team_members = []
    for permission_obj, first_name, last_name, email, profile_data in team_data:
        # Parse profile_data if it's JSON
        profile = {}
        if profile_data:
            try:
                profile = json.loads(profile_data)
            except:
                pass

        member_data = {
            "user_id": str(permission_obj.user_id),
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "permission_level": permission_obj.permission_level.value,
            "is_active": permission_obj.is_active,
            "is_pending": False,  # You may need to implement invite system
            "created_at": permission_obj.created_at.isoformat(),
            "expires_at": permission_obj.expires_at.isoformat() if permission_obj.expires_at else None,
            "notes": permission_obj.notes,
            # Additional fields from profile
            "archaeological_role": profile.get("archaeological_role"),
            "specialization": profile.get("specialization"),
            "institution": profile.get("institution"),
            # Stats (you may need to implement these)
            "photos_uploaded": 0,  # Query from Photo model
            "last_login": None,  # From User model if you track this
        }

        team_members.append(member_data)

    return {
        "team_members": team_members,
        "total": len(team_members)
    }


# === NUOVI ENDPOINTS PER STREAMING MINIO ===

@sites_router.get("/{site_id}/photos/{photo_id}/stream")
async def stream_photo_from_minio(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Stream foto da MinIO con URL pre-firmato"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo or not photo.file_path.startswith('minio://'):
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Genera URL streaming temporaneo
    stream_url = await archaeological_minio_service.get_photo_stream_url(photo.file_path)

    if not stream_url:
        raise HTTPException(status_code=500, detail="Errore generazione URL")

    # Redirect al URL MinIO per streaming diretto
    return RedirectResponse(url=stream_url, status_code=302)


@sites_router.get("/{site_id}/photos/{photo_id}/thumbnail")
async def get_photo_thumbnail(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni thumbnail foto da MinIO"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Genera URL thumbnail
    thumbnail_url = await archaeological_minio_service.get_thumbnail_url(str(photo_id))

    if not thumbnail_url:
        raise HTTPException(status_code=500, detail="Errore generazione URL thumbnail")

    # Redirect al URL MinIO per thumbnail
    return RedirectResponse(url=thumbnail_url, status_code=302)


@sites_router.get("/{site_id}/photos/{photo_id}/full")
async def get_photo_full(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni immagine completa foto da MinIO"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Genera URL immagine completa
    full_url = await archaeological_minio_service.get_photo_stream_url(photo.file_path)

    if not full_url:
        raise HTTPException(status_code=500, detail="Errore generazione URL immagine")

    # Redirect al URL MinIO per immagine completa
    return RedirectResponse(url=full_url, status_code=302)


@sites_router.get("/{site_id}/api/storage/stats")
async def get_site_storage_stats(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni statistiche storage del sito con gestione avanzata"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    try:
        # Ottieni statistiche da MinIO archeologico
        site_stats = await archaeological_minio_service.get_storage_stats(str(site_id))
        
        # Ottieni statistiche globali storage
        global_stats = await storage_management_service.get_storage_usage()
        
        # Controlla se storage è quasi pieno (>85%)
        storage_warning = False
        if global_stats.get('total_size_gb', 0) > 0:
            # Assumiamo un limite di 10GB per MinIO locale
            storage_usage_percent = (global_stats['total_size_gb'] / 10.0) * 100
            storage_warning = storage_usage_percent > 85
        
        combined_stats = {
            **site_stats,
            'global_storage': global_stats,
            'storage_warning': storage_warning,
            'storage_usage_percent': min(100, storage_usage_percent) if 'storage_usage_percent' in locals() else 0
        }
        
        return JSONResponse(combined_stats)
        
    except Exception as e:
        logger.error(f"Error getting storage stats: {e}")
        return JSONResponse({
            'site_id': str(site_id),
            'total_size_mb': 0,
            'photo_count': 0,
            'document_count': 0,
            'total_files': 0,
            'storage_warning': True,
            'error': str(e)
        })


@sites_router.post("/{site_id}/api/storage/cleanup")
async def emergency_storage_cleanup(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Cleanup di emergenza dello storage MinIO"""
    site, permission = site_access

    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Solo gli amministratori possono eseguire il cleanup")

    try:
        # Assicurati che tutti i bucket esistano
        bucket_check = await storage_management_service.ensure_buckets_exist()
        logger.info(f"Bucket check result: {bucket_check}")
        
        # Esegui cleanup di emergenza
        cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=500)
        
        return JSONResponse({
            'success': cleanup_result['success'],
            'total_freed_mb': cleanup_result['total_freed_mb'],
            'cleanup_actions': cleanup_result['cleanup_actions'],
            'bucket_check': bucket_check,
            'message': f"Cleanup completato: {cleanup_result['total_freed_mb']}MB liberati"
        })
        
    except Exception as e:
        logger.error(f"Emergency cleanup failed: {e}")
        return JSONResponse({
            'success': False,
            'total_freed_mb': 0,
            'cleanup_actions': [],
            'error': str(e),
            'message': f"Cleanup fallito: {str(e)}"
        }, status_code=500)


@sites_router.get("/{site_id}/api/storage/health")
async def check_storage_health(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Controlla lo stato di salute dello storage MinIO"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    try:
        # Controlla i bucket
        bucket_status = await storage_management_service.ensure_buckets_exist()
        
        # Controlla l'utilizzo dello storage
        storage_usage = await storage_management_service.get_storage_usage()
        
        # Determina lo stato di salute
        health_status = "healthy"
        issues = []
        
        if bucket_status['errors']:
            health_status = "warning"
            issues.append(f"{len(bucket_status['errors'])} bucket errors")
        
        if storage_usage.get('total_size_gb', 0) > 8:  # >80% di 10GB
            health_status = "critical"
            issues.append("Storage usage critical (>80%)")
        elif storage_usage.get('total_size_gb', 0) > 6:  # >60% di 10GB
            if health_status == "healthy":
                health_status = "warning"
            issues.append("Storage usage high (>60%)")
        
        return JSONResponse({
            'status': health_status,
            'issues': issues,
            'bucket_status': bucket_status,
            'storage_usage': storage_usage,
            'recommendations': [
                "Run emergency cleanup if storage >85%",
                "Check for orphaned files",
                "Consider archiving old photos"
            ] if health_status != "healthy" else []
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse({
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'bucket_status': {},
            'storage_usage': {},
            'recommendations': ["Contact system administrator"]
        }, status_code=500)


@sites_router.get("/{site_id}/api/photos/search")
async def search_photos_by_metadata(
        site_id: UUID,
        material: Optional[str] = None,
        inventory_number: Optional[str] = None,
        excavation_area: Optional[str] = None,
        chronology_period: Optional[str] = None,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Cerca foto per metadati archeologici"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Cerca foto in MinIO
    search_results = await archaeological_minio_service.search_photos_by_metadata(
        site_id=str(site_id),
        material=material,
        inventory_number=inventory_number,
        excavation_area=excavation_area,
        chronology_period=chronology_period
    )

    return JSONResponse({
        "results": search_results,
        "total": len(search_results)
    })


# === DEEP ZOOM ENDPOINTS ===

@sites_router.get("/{site_id}/photos/{photo_id}/deepzoom/info")
async def get_deep_zoom_info(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni informazioni deep zoom per una foto"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Ottieni info deep zoom
    deep_zoom_info = await archaeological_minio_service.get_deep_zoom_info(str(site_id), str(photo_id))

    if not deep_zoom_info:
        # Return a proper JSON response indicating deep zoom is not available
        return JSONResponse({
            "photo_id": str(photo_id),
            "site_id": str(site_id),
            "available": False,
            "message": "Deep zoom tiles not generated for this photo",
            "width": 0,
            "height": 0,
            "levels": 0,
            "tile_size": 256,
            "total_tiles": 0
        })

    return JSONResponse(deep_zoom_info)


@sites_router.get("/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.{format}")
async def get_deep_zoom_tile(
        site_id: UUID,
        photo_id: UUID,
        level: int,
        x: int,
        y: int,
        format: str,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """FIXED: Ottieni singolo tile deep zoom con supporto formato dinamico (jpg/png)"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Validate format
    if format not in ['jpg', 'png', 'jpeg']:
        raise HTTPException(status_code=400, detail="Formato tile non supportato")

    # Ottieni URL del tile
    tile_url = await archaeological_minio_service.get_tile_url(str(site_id), str(photo_id), level, x, y)

    if not tile_url:
        raise HTTPException(status_code=404, detail="Tile non trovato")

    # Redirect al tile
    return RedirectResponse(url=tile_url, status_code=302)


# FIXED: Aggiungi endpoint legacy per backward compatibility
@sites_router.get("/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.jpg")
async def get_deep_zoom_tile_jpg(
        site_id: UUID,
        photo_id: UUID,
        level: int,
        x: int,
        y: int,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Legacy endpoint per tile JPG - redirect al nuovo endpoint dinamico"""
    return await get_deep_zoom_tile(site_id, photo_id, level, x, y, "jpg", site_access, db)


@sites_router.get("/{site_id}/photos/{photo_id}/deepzoom/tiles/{level}/{x}_{y}.png")
async def get_deep_zoom_tile_png(
        site_id: UUID,
        photo_id: UUID,
        level: int,
        x: int,
        y: int,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Legacy endpoint per tile PNG - redirect al nuovo endpoint dinamico"""
    return await get_deep_zoom_tile(site_id, photo_id, level, x, y, "png", site_access, db)


@sites_router.post("/{site_id}/photos/{photo_id}/deepzoom/process")
async def process_deep_zoom(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Processa foto esistente per generare deep zoom tiles"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Scarica foto da MinIO per processamento
    try:
        photo_data = await archaeological_minio_service.get_file(photo.file_path)

        # Processa con deep zoom
        from fastapi import UploadFile
        import io

        temp_file = UploadFile(
            filename=photo.filename,
            file=io.BytesIO(photo_data)
        )

        result = await deep_zoom_minio_service.process_and_upload_tiles(
            photo_id=str(photo_id),
            original_file=temp_file,
            site_id=str(site_id),
            archaeological_metadata={
                'inventory_number': photo.inventory_number,
                'excavation_area': photo.excavation_area,
                'material': photo.material,
                'chronology_period': photo.chronology_period
            }
        )

        # Aggiorna database con info deep zoom
        photo.has_deep_zoom = True
        photo.deep_zoom_levels = result['levels']
        photo.deep_zoom_tile_count = result['total_tiles']
        await db.commit()

        return JSONResponse({
            "message": "Deep zoom processing completato",
            "photo_id": str(photo_id),
            "tiles_generated": result['total_tiles'],
            "levels": result['levels'],
            "metadata_url": result['metadata_url']
        })

    except Exception as e:
        logger.error(f"Deep zoom processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Deep zoom processing failed: {str(e)}")


@sites_router.get("/{site_id}/photos/{photo_id}/deepzoom/status")
async def get_deep_zoom_processing_status(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni status di elaborazione deep zoom per una foto"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Trova foto nel database
    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Ottieni status da MinIO se disponibile
    minio_status = await deep_zoom_minio_service.get_processing_status(str(site_id), str(photo_id))

    return JSONResponse({
        "photo_id": str(photo_id),
        "site_id": str(site_id),
        "status": photo.deep_zoom_status,
        "has_deep_zoom": photo.has_deep_zoom,
        "levels": photo.deep_zoom_levels,
        "tile_count": photo.deep_zoom_tile_count,
        "processed_at": photo.deep_zoom_processed_at.isoformat() if photo.deep_zoom_processed_at else None,
        "minio_status": minio_status
    })


@sites_router.get("/{site_id}/api/photos/processing-queue")
async def get_processing_queue_status(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """
    FIXED: Endpoint per controllare lo stato della coda di processamento
    Utile per verificare che il background processing non blocchi gli upload
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Ottieni foto in processing o scheduled
    processing_query = select(Photo).where(
        and_(
            Photo.site_id == site_id,
            Photo.deep_zoom_status.in_(['scheduled', 'processing'])
        )
    ).order_by(Photo.created.desc())
    
    processing_photos = await db.execute(processing_query)
    processing_photos = processing_photos.scalars().all()

    # Ottieni foto completate recentemente (ultime 24 ore)
    recent_completed_query = select(Photo).where(
        and_(
            Photo.site_id == site_id,
            Photo.deep_zoom_status == 'completed',
            Photo.deep_zoom_processed_at >= datetime.now() - timedelta(hours=24)
        )
    ).order_by(Photo.deep_zoom_processed_at.desc()).limit(10)
    
    completed_photos = await db.execute(recent_completed_query)
    completed_photos = completed_photos.scalars().all()

    return JSONResponse({
        "site_id": str(site_id),
        "processing_queue": [
            {
                "photo_id": str(photo.id),
                "filename": photo.filename,
                "status": photo.deep_zoom_status,
                "created_at": photo.created.isoformat(),
                "width": photo.width,
                "height": photo.height
            }
            for photo in processing_photos
        ],
        "recent_completed": [
            {
                "photo_id": str(photo.id),
                "filename": photo.filename,
                "status": photo.deep_zoom_status,
                "completed_at": photo.deep_zoom_processed_at.isoformat() if photo.deep_zoom_processed_at else None,
                "tile_count": photo.deep_zoom_tile_count,
                "levels": photo.deep_zoom_levels
            }
            for photo in completed_photos
        ],
        "queue_length": len(processing_photos),
        "completed_today": len(completed_photos)
    })


@sites_router.put("/{site_id}/photos/{photo_id}/update")
async def update_photo(
        site_id: UUID,
        photo_id: UUID,
        request: Request,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Aggiorna metadati foto archeologica

    Args:
        site_id: ID del sito archeologico
        photo_id: ID della foto da aggiornare
        update_data: Dati da aggiornare
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Parse JSON request body
    try:
        update_data = await request.json()
        logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Received data: {update_data}")
    except Exception as e:
        logger.error(f"PUT /sites/{site_id}/photos/{photo_id}/update - JSON parsing error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")

    # Verifica che la foto appartenga al sito
    photo_query = select(Photo).where(
        and_(Photo.id == photo_id, Photo.site_id == site_id)
    )
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata nel sito")

    # Campi aggiornabili (escludiamo campi tecnici e di sistema)
    updatable_fields = {
        'title', 'description', 'keywords', 'photo_type', 'photographer',
        'inventory_number', 'old_inventory_number', 'catalog_number',
        'excavation_area', 'stratigraphic_unit', 'grid_square', 'depth_level',
        'find_date', 'finder', 'excavation_campaign',
        'material', 'material_details', 'object_type', 'object_function',
        'length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams',
        'chronology_period', 'chronology_culture',
        'dating_from', 'dating_to', 'dating_notes',
        'conservation_status', 'conservation_notes', 'restoration_history',
        'bibliography', 'comparative_references', 'external_links',
        'copyright_holder', 'license_type', 'usage_rights',
        'validation_notes'
    }

    # Filtra solo i campi che sono stati forniti e sono aggiornabili
    filtered_data = {}
    for field in updatable_fields:
        if field in update_data and update_data[field] is not None:
            value = update_data[field]

            # Gestione campi numerici - converti stringhe vuote in None
            if field in ['length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams', 'depth_level']:
                if value == '' or value == 'null' or value == 'None':
                    filtered_data[field] = None
                else:
                    try:
                        # Prova a convertire in float
                        filtered_data[field] = float(value) if value else None
                    except (ValueError, TypeError):
                        filtered_data[field] = None
            else:
                filtered_data[field] = value

    # Gestione campi enum
    if 'photo_type' in filtered_data and filtered_data['photo_type']:
        try:
            filtered_data['photo_type'] = PhotoType(filtered_data['photo_type'])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo foto non valido: {filtered_data['photo_type']}"
            )

    if 'material' in filtered_data and filtered_data['material']:
        try:
            filtered_data['material'] = MaterialType(filtered_data['material'])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Materiale non valido: {filtered_data['material']}"
            )

    if 'conservation_status' in filtered_data and filtered_data['conservation_status']:
        try:
            filtered_data['conservation_status'] = ConservationStatus(filtered_data['conservation_status'])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Stato di conservazione non valido: {filtered_data['conservation_status']}"
            )

    # Gestione date
    if 'find_date' in filtered_data and filtered_data['find_date']:
        try:
            if isinstance(filtered_data['find_date'], str):
                if filtered_data['find_date'] == '' or filtered_data['find_date'] == 'null' or filtered_data[
                    'find_date'] == 'None':
                    filtered_data['find_date'] = None
                else:
                    # Prova diversi formati di data
                    try:
                        filtered_data['find_date'] = datetime.fromisoformat(filtered_data['find_date'])
                    except ValueError:
                        # Prova formato YYYY-MM-DD
                        try:
                            filtered_data['find_date'] = datetime.strptime(filtered_data['find_date'], '%Y-%m-%d')
                        except ValueError:
                            raise HTTPException(
                                status_code=400,
                                detail="Formato data non valido per find_date"
                            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Formato data non valido per find_date"
            )

    # Gestione JSON fields
    if 'keywords' in filtered_data:
        if isinstance(filtered_data['keywords'], str) and filtered_data['keywords']:
            # Convert comma-separated string to list, then to JSON
            keywords_list = [kw.strip() for kw in filtered_data['keywords'].split(',') if kw.strip()]
            filtered_data['keywords'] = json.dumps(keywords_list)
        elif isinstance(filtered_data['keywords'], list):
            filtered_data['keywords'] = json.dumps(filtered_data['keywords'])
        elif not filtered_data['keywords']:
            filtered_data['keywords'] = None

    if 'external_links' in filtered_data and isinstance(filtered_data['external_links'], list):
        filtered_data['external_links'] = json.dumps(filtered_data['external_links'])

    # Log filtered data before applying changes
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Filtered data to apply: {filtered_data}")
    
    # Aggiorna i campi della foto
    for field, value in filtered_data.items():
        old_value = getattr(photo, field, None)
        # Assicurati che i valori vuoti siano None per i campi nullable
        if value == '' or value == 'null' or value == 'None':
            setattr(photo, field, None)
            logger.info(f"PUT - Field '{field}': '{old_value}' -> None")
        else:
            setattr(photo, field, value)
            logger.info(f"PUT - Field '{field}': '{old_value}' -> '{value}'")

    # Aggiorna timestamp
    photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Photo updated timestamp: {photo.updated}")

    # Log dell'attività
    await log_user_activity(
        db=db,
        user_id=current_user_id,
        site_id=site_id,
        activity_type="UPDATE",
        activity_desc=f"Aggiornati metadati foto: {photo.filename}",
        extra_data=json.dumps({
            "photo_id": str(photo_id),
            "fields_updated": list(filtered_data.keys())
        })
    )

    await db.commit()
    await db.refresh(photo)
    
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Photo successfully committed to database")
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Updated fields: {list(filtered_data.keys())}")
    
    # Create response with photo data to verify changes
    response_data = {
        "message": "Foto aggiornata con successo",
        "photo_id": str(photo_id),
        "updated_fields": list(filtered_data.keys()),
        "photo_data": photo.to_dict()
    }
    
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Response: {response_data}")
    return response_data


@sites_router.delete("/{site_id}/photos/{photo_id}")
async def delete_photo(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """
    Elimina foto dal sito archeologico

    Args:
        site_id: ID del sito archeologico
        photo_id: ID della foto da eliminare
    """
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Verifica che la foto appartenga al sito
    photo_query = select(Photo).where(
        and_(Photo.id == photo_id, Photo.site_id == site_id)
    )
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata nel sito")

    try:
        # Salva informazioni per log prima dell'eliminazione
        photo_filename = photo.filename
        photo_path = photo.file_path
        thumbnail_path = photo.thumbnail_path

        # Elimina record dal database
        await db.delete(photo)
        await db.commit()

        # Elimina file fisici se esistono
        try:
            # Elimina file originale
            if photo_path:
                if '/' in photo_path:
                    # File su MinIO archeologico
                    try:
                        success = await archaeological_minio_service.remove_file(photo_path)
                        if success:
                            logger.info(f"File eliminato da Archaeological MinIO: {photo_path}")
                        else:
                            logger.warning(f"Impossibile eliminare file: {photo_path}")
                    except Exception as e:
                        logger.warning(f"Errore eliminazione file Archaeological MinIO {photo_path}: {e}")
                elif photo_path.startswith("storage/") or photo_path.startswith("app/static/uploads/"):
                    # File locale
                    file_path = Path(photo_path)
                    if file_path.exists():
                        file_path.unlink()
                        logger.info(f"File locale eliminato: {file_path}")

            # Elimina thumbnail
            if thumbnail_path:
                if thumbnail_path.startswith("thumbnails/"):
                    # Thumbnail su MinIO (archaeological service)
                    try:
                        # Usa il metodo corretto del servizio archeologico
                        success = await archaeological_minio_service.remove_object_from_bucket(
                            archaeological_minio_service.buckets['thumbnails'],
                            thumbnail_path
                        )
                        if success:
                            logger.info(f"Thumbnail eliminato da Archaeological MinIO: {thumbnail_path}")
                        else:
                            logger.warning(f"Impossibile eliminare thumbnail: {thumbnail_path}")
                    except Exception as e:
                        logger.warning(f"Errore eliminazione thumbnail Archaeological MinIO {thumbnail_path}: {e}")
                elif thumbnail_path.startswith("storage/thumbnails/"):
                    # Thumbnail locale
                    thumbnail_file_path = Path(thumbnail_path)
                    if thumbnail_file_path.exists():
                        thumbnail_file_path.unlink()
                        logger.info(f"Thumbnail locale eliminato: {thumbnail_file_path}")

        except Exception as e:
            logger.warning(f"Errore durante eliminazione file fisici: {e}")
            # Non bloccare l'operazione se l'eliminazione dei file fallisce

        # Log dell'attività
        await log_user_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="DELETE",
            activity_desc=f"Eliminata foto: {photo_filename}",
            extra_data=json.dumps({
                "photo_id": str(photo_id),
                "filename": photo_filename,
                "file_path": photo_path,
                "thumbnail_path": thumbnail_path
            })
        )

        return {
            "message": "Foto eliminata con successo",
            "photo_id": str(photo_id),
            "filename": photo_filename
        }

    except Exception as e:
        logger.error(f"Errore durante eliminazione foto {photo_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante eliminazione foto: {str(e)}"
        )


@sites_router.post("/{site_id}/api/photos/bulk-delete")
async def bulk_delete_photos(
        site_id: UUID,
        delete_data: dict,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Elimina più foto in blocco"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Correzione critica: Converti gli ID string in UUID
    photo_ids_raw = delete_data.get("photo_ids", [])
    if not photo_ids_raw:
        raise HTTPException(status_code=400, detail="Nessuna foto selezionata")

    try:
        # Converti string ID in UUID objects
        photo_ids = []
        for photo_id in photo_ids_raw:
            if isinstance(photo_id, str):
                try:
                    photo_ids.append(UUID(photo_id))
                except ValueError:
                    logger.warning(f"Invalid UUID format: {photo_id}")
                    continue
            elif isinstance(photo_id, UUID):
                photo_ids.append(photo_id)
            else:
                logger.warning(f"Unexpected photo_id type: {type(photo_id)} - {photo_id}")

        if not photo_ids:
            raise HTTPException(status_code=400, detail="Nessun ID foto valido")

        logger.info(f"Bulk delete: processing {len(photo_ids)} photos for site {site_id}")

        # Get photos to delete
        photos_query = select(Photo).where(and_(
            Photo.site_id == site_id,
            Photo.id.in_(photo_ids)
        ))
        photos = await db.execute(photos_query)
        photos = photos.scalars().all()

        if not photos:
            raise HTTPException(status_code=404, detail="Nessuna foto trovata con gli ID specificati")

        deleted_count = 0
        for photo in photos:
            try:
                # Save info for logging
                photo_filename = photo.filename
                photo_path = photo.file_path
                thumbnail_path = photo.thumbnail_path

                # Delete files
                if photo_path and '/' in photo_path:
                    try:
                        success = await archaeological_minio_service.remove_file(photo_path)
                        if success:
                            logger.info(f"File deleted from MinIO: {photo_path}")
                        else:
                            logger.warning(f"Could not delete file: {photo_path}")
                    except Exception as e:
                        logger.warning(f"Error deleting file {photo_path}: {e}")

                if thumbnail_path and thumbnail_path.startswith("thumbnails/"):
                    try:
                        success = await archaeological_minio_service.remove_object_from_bucket(
                            archaeological_minio_service.buckets["thumbnails"],
                            thumbnail_path
                        )
                        if success:
                            logger.info(f"Thumbnail deleted from MinIO: {thumbnail_path}")
                        else:
                            logger.warning(f"Could not delete thumbnail: {thumbnail_path}")
                    except Exception as e:
                        logger.warning(f"Error deleting thumbnail {thumbnail_path}: {e}")

                # Delete from database
                await db.delete(photo)
                deleted_count += 1

                # CORREZIONE: Log activity con creazione diretta dell'oggetto
                activity = UserActivity(
                    user_id=current_user_id,
                    site_id=site_id,
                    activity_type="DELETE",
                    activity_desc=f"Eliminazione massiva foto {photo_filename}",
                    extra_data=json.dumps({  # IMPORTANTE: Serializza come JSON string
                        "photo_id": str(photo.id),
                        "bulk_operation": True,
                        "filename": photo_filename
                    })
                )

                db.add(activity)

            except Exception as e:
                logger.warning(f"Error deleting photo {photo.id}: {e}")
                continue

        await db.commit()

        return JSONResponse({
            "message": f"{deleted_count} foto eliminate con successo",
            "deleted_count": deleted_count
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore eliminazione in blocco: {str(e)}")


@sites_router.post("/{site_id}/api/photos/bulk-update")
async def bulk_update_photos(
        site_id: UUID,
        update_data: dict,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna più foto in blocco con supporto completo per metadati archeologici"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Correzione critica: Converti gli ID string in UUID
    photo_ids_raw = update_data.get("photo_ids", [])
    metadata = update_data.get("metadata", {})
    
    # Legacy support for tag operations
    add_tags = update_data.get("add_tags", [])
    remove_tags = update_data.get("remove_tags", [])

    if not photo_ids_raw:
        raise HTTPException(status_code=400, detail="Nessuna foto selezionata")

    logger.info(f"Bulk update received data: {update_data}")

    try:
        # Converti string ID in UUID objects
        photo_ids = []
        for photo_id in photo_ids_raw:
            if isinstance(photo_id, str):
                try:
                    photo_ids.append(UUID(photo_id))
                except ValueError:
                    logger.warning(f"Invalid UUID format: {photo_id}")
                    continue
            elif isinstance(photo_id, UUID):
                photo_ids.append(photo_id)
            else:
                logger.warning(f"Unexpected photo_id type: {type(photo_id)} - {photo_id}")

        if not photo_ids:
            raise HTTPException(status_code=400, detail="Nessun ID foto valido")

        logger.info(f"Bulk update: processing {len(photo_ids)} photos for site {site_id}")

        # Get photos to update
        photos_query = select(Photo).where(and_(
            Photo.site_id == site_id,
            Photo.id.in_(photo_ids)
        ))
        photos = await db.execute(photos_query)
        photos = photos.scalars().all()

        if not photos:
            raise HTTPException(status_code=404, detail="Nessuna foto trovata con gli ID specificati")

        # Campi aggiornabili (stessi del singolo update)
        updatable_fields = {
            'title', 'description', 'keywords', 'photo_type', 'photographer',
            'inventory_number', 'old_inventory_number', 'catalog_number',
            'excavation_area', 'stratigraphic_unit', 'grid_square', 'depth_level',
            'find_date', 'finder', 'excavation_campaign',
            'material', 'material_details', 'object_type', 'object_function',
            'length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams',
            'chronology_period', 'chronology_culture',
            'dating_from', 'dating_to', 'dating_notes',
            'conservation_status', 'conservation_notes', 'restoration_history',
            'bibliography', 'comparative_references', 'external_links',
            'copyright_holder', 'license_type', 'usage_rights',
            'validation_notes'
        }

        # Filtra solo i campi che sono stati forniti e sono aggiornabili
        filtered_metadata = {}
        for field in updatable_fields:
            if field in metadata and metadata[field] is not None and metadata[field] != '':
                value = metadata[field]
                
                # Gestione campi numerici
                if field in ['length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams', 'depth_level']:
                    try:
                        filtered_metadata[field] = float(value) if value else None
                    except (ValueError, TypeError):
                        filtered_metadata[field] = None
                else:
                    filtered_metadata[field] = value

        # Gestione campi enum
        if 'photo_type' in filtered_metadata and filtered_metadata['photo_type']:
            try:
                filtered_metadata['photo_type'] = PhotoType(filtered_metadata['photo_type'])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo foto non valido: {filtered_metadata['photo_type']}"
                )

        if 'material' in filtered_metadata and filtered_metadata['material']:
            try:
                filtered_metadata['material'] = MaterialType(filtered_metadata['material'])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Materiale non valido: {filtered_metadata['material']}"
                )

        if 'conservation_status' in filtered_metadata and filtered_metadata['conservation_status']:
            try:
                filtered_metadata['conservation_status'] = ConservationStatus(filtered_metadata['conservation_status'])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stato di conservazione non valido: {filtered_metadata['conservation_status']}"
                )

        # Gestione date
        if 'find_date' in filtered_metadata and filtered_metadata['find_date']:
            try:
                if isinstance(filtered_metadata['find_date'], str):
                    try:
                        filtered_metadata['find_date'] = datetime.fromisoformat(filtered_metadata['find_date'])
                    except ValueError:
                        try:
                            filtered_metadata['find_date'] = datetime.strptime(filtered_metadata['find_date'], '%Y-%m-%d')
                        except ValueError:
                            raise HTTPException(
                                status_code=400,
                                detail="Formato data non valido per find_date"
                            )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Formato data non valido per find_date"
                )

        # Gestione JSON fields
        if 'keywords' in filtered_metadata:
            if isinstance(filtered_metadata['keywords'], str) and filtered_metadata['keywords']:
                keywords_list = [kw.strip() for kw in filtered_metadata['keywords'].split(',') if kw.strip()]
                filtered_metadata['keywords'] = json.dumps(keywords_list)
            elif isinstance(filtered_metadata['keywords'], list):
                filtered_metadata['keywords'] = json.dumps(filtered_metadata['keywords'])

        if 'external_links' in filtered_metadata and isinstance(filtered_metadata['external_links'], list):
            filtered_metadata['external_links'] = json.dumps(filtered_metadata['external_links'])

        logger.info(f"Bulk update: filtered metadata to apply: {filtered_metadata}")

        updated_count = 0
        updated_fields = []
        
        for photo in photos:
            try:
                # Applica metadati archeologici
                for field, value in filtered_metadata.items():
                    old_value = getattr(photo, field, None)
                    setattr(photo, field, value)
                    if field not in updated_fields:
                        updated_fields.append(field)
                    logger.info(f"Bulk update - Photo {photo.id} - Field '{field}': '{old_value}' -> '{value}'")

                # Legacy support: gestisci ancora i tag se forniti
                if add_tags or remove_tags:
                    current_tags = getattr(photo, 'tags', None) or []
                    if isinstance(current_tags, str):
                        try:
                            current_tags = json.loads(current_tags)
                        except:
                            current_tags = []

                    # Add new tags
                    for tag in add_tags:
                        if tag not in current_tags:
                            current_tags.append(tag)

                    # Remove tags
                    for tag in remove_tags:
                        if tag in current_tags:
                            current_tags.remove(tag)

                    if hasattr(photo, 'tags'):
                        photo.tags = current_tags
                        if 'tags' not in updated_fields:
                            updated_fields.append('tags')

                # Aggiorna timestamp
                photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
                updated_count += 1

            except Exception as e:
                logger.warning(f"Error updating photo {photo.id}: {e}")
                continue

        # Log activity for bulk operation
        await log_user_activity(
            db=db,
            user_id=current_user_id,
            site_id=site_id,
            activity_type="BULK_UPDATE",
            activity_desc=f"Aggiornamento massivo di {updated_count} foto",
            extra_data=json.dumps({
                "photo_count": updated_count,
                "photo_ids": [str(pid) for pid in photo_ids],
                "updated_fields": updated_fields,
                "metadata_fields": list(filtered_metadata.keys()),
                "add_tags": add_tags,
                "remove_tags": remove_tags
            })
        )

        await db.commit()

        return JSONResponse({
            "message": f"{updated_count} foto aggiornate con successo",
            "updated_count": updated_count,
            "updated_fields": updated_fields
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk update error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore aggiornamento in blocco: {str(e)}")


@sites_router.put("/{site_id}/team/{user_id}/update-permissions")
async def update_team_member_permissions(
        site_id: UUID,
        user_id: UUID,
        permission_data: dict,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Update team member permissions"""
    site, permission = site_access

    if not permission.can_admin():
        raise HTTPException(status_code=403, detail="Solo gli amministratori possono modificare i permessi")

    # Usa UserSitePermission invece di UserSite
    member_query = select(UserSitePermission).where(
        and_(UserSitePermission.site_id == site_id, UserSitePermission.user_id == user_id)
    )
    member = await db.execute(member_query)
    member = member.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Membro del team non trovato")

    # Update permissions
    member.permission_level = PermissionLevel(permission_data.get('permission_level', member.permission_level.value))
    member.is_active = permission_data.get('is_active', member.is_active)

    # Update additional fields
    if 'notes' in permission_data:
        member.notes = permission_data['notes']

    # Update expiry if specified
    if permission_data.get('access_duration') != 'no_change':
        if permission_data.get('expires_at'):
            member.expires_at = datetime.fromisoformat(permission_data['expires_at'])
        elif permission_data.get('access_duration') == 'permanent':
            member.expires_at = None

    member.updated_at = datetime.now(timezone.utc)

    await db.commit()

    return {"message": "Permessi aggiornati con successo"}



# === FUNZIONI HELPER ===

async def log_user_activity(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        activity_type: str,
        activity_desc: str,
        extra_data: Dict[str, Any] = None
):
    """Log attività utente nel sistema"""
    try:
        # CORREZIONE: Serializza extra_data come JSON string
        extra_data_json = None
        if extra_data:
            extra_data_json = json.dumps(extra_data)

        # Crea attività
        activity = UserActivity(
            user_id=user_id,
            site_id=site_id,
            activity_type=activity_type,
            activity_desc=activity_desc,
            extra_data=extra_data_json  # Passa JSON string, non dict
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Activity logged: {activity_type} by {user_id}")

    except Exception as e:
        logger.error(f"Error logging activity: {e}")
        # Non bloccare l'operazione principale se il log fallisce
        await db.rollback()


async def get_site_statistics(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """Calcola statistiche del sito"""

    # Conta foto
    photos_count = await db.execute(
        select(func.count(Photo.id)).where(Photo.site_id == site_id)
    )
    photos_count = photos_count.scalar() or 0

    # Conta utenti autorizzati
    users_count = await db.execute(
        select(func.count(UserSitePermission.id)).where(
            and_(
                UserSitePermission.site_id == site_id,
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
                Photo.site_id == site_id,
                Photo.created >= last_month
            )
        )
    )
    recent_photos = recent_photos.scalar() or 0

    # Storage utilizzato (MB)
    storage_query = await db.execute(
        select(func.sum(Photo.file_size)).where(Photo.site_id == site_id)
    )
    storage_mb = (storage_query.scalar() or 0) / (1024 * 1024)

    return {
        "photos_count": photos_count,
        "users_count": users_count,
        "recent_photos": recent_photos,
        "storage_mb": round(storage_mb, 2),
        "last_updated": datetime.now().isoformat()
    }


async def get_recent_activities(db: AsyncSession, site_id: UUID, limit: int = 10) -> List[Dict]:
    """Recupera attività recenti del sito"""
    activities_query = (
        select(UserActivity, User)
        .outerjoin(User, UserActivity.user_id == User.id)
        .where(UserActivity.site_id == site_id)
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


async def get_recent_photos(db: AsyncSession, site_id: UUID, limit: int = 6) -> List[Dict]:
    """Recupera foto recenti del sito"""
    photos_query = select(Photo).where(
        Photo.site_id == site_id
    ).order_by(Photo.created.desc()).limit(limit)

    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    return [
        {
            "id": str(photo.id),
            "filename": photo.filename,
            "thumbnail_url": f"/photos/{photo.id}/thumbnail",
            "full_url": f"/photos/{photo.id}/full",
            "photo_type": photo.photo_type.value if photo.photo_type else None,
            "created_at": photo.created.isoformat()
        }
        for photo in photos
    ]


async def get_site_team(db: AsyncSession, site_id: UUID) -> List[Dict]:
    """Recupera team del sito"""
    from sqlalchemy.orm import selectinload
    
    team_query = select(User, UserSitePermission).join(
        UserSitePermission, User.id == UserSitePermission.user_id
    ).options(selectinload(User.profile)).where(
        and_(
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True
        )
    ).order_by(UserSitePermission.permission_level.desc())

    team = await db.execute(team_query)
    team = team.all()

    return [
        {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": getattr(user, 'full_name', f"{user.first_name} {user.last_name}"),
            "permission_level": permission.permission_level.value,
            "permission_display": permission.permission_level.value.replace('_', ' ').title(),
            "granted_at": permission.created_at.isoformat()
        }
        for user, permission in team
    ]


# === ROUTES ICCD - CATALOGAZIONE ARCHEOLOGICA STANDARDIZZATA ===

@sites_router.get("/{site_id}/iccd", response_class=HTMLResponse)
async def site_iccd_records(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Redirect to hierarchical ICCD system."""
    # Redirect to the new hierarchical system
    return RedirectResponse(url=f"/sites/{site_id}/iccd/hierarchy", status_code=302)


@sites_router.get("/{site_id}/iccd/hierarchy", response_class=HTMLResponse)
async def site_iccd_hierarchy(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Sistema gerarchico ICCD completo del sito archeologico."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }
    
    return templates.TemplateResponse("sites/iccd_hierarchy.html", context)


@sites_router.get("/{site_id}/iccd/records", response_class=HTMLResponse)
async def site_iccd_records_list(
        request: Request,
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Lista schede ICCD del sito archeologico (legacy endpoint)."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }
    
    # Usa template completo per visualizzare lista schede ICCD
    return templates.TemplateResponse("sites/iccd_records.html", context)


@sites_router.get("/{site_id}/iccd/new", response_class=HTMLResponse)
async def new_iccd_record(
        request: Request,
        site_id: UUID,
        schema_type: str = "RA",
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Form per creare nuova scheda ICCD."""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()

    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "schema_type": schema_type,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }

    # Seleziona template in base al tipo schema
    template_name = "sites/iccd_ra_300_form.html"  # Default RA
    if schema_type == "SI":
        template_name = "sites/iccd_si_300_form.html"
    elif schema_type == "CA":
        template_name = "sites/iccd_ca_300_form.html"  # Per futuro

    return templates.TemplateResponse(template_name, context)


@sites_router.get("/{site_id}/iccd/{record_id}", response_class=HTMLResponse)
async def view_iccd_record(
        request: Request,
        site_id: UUID,
        record_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Visualizza scheda ICCD specifica."""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    # Recupera record ICCD dal database
    try:
        from app.models.iccd_records import ICCDBaseRecord
        
        record_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == record_id,
                ICCDBaseRecord.site_id == site_id
            )
        )
        result = await db.execute(record_query)
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
        
        # Convert to dict for template
        record_data = {
            "id": str(record.id),
            "schema_type": record.schema_type,
            "nct": f"{record.nct_region}{record.nct_number}{record.nct_suffix or ''}",
            "iccd_data": record.iccd_data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading ICCD record {record_id}: {e}")
        raise HTTPException(status_code=500, detail="Errore caricamento scheda ICCD")
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "record": record_data,
        "record_id": str(record_id),
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }
    
    return templates.TemplateResponse("sites/iccd_view.html", context)


@sites_router.get("/{site_id}/iccd/{record_id}/edit", response_class=HTMLResponse)
async def edit_iccd_record(
        request: Request,
        site_id: UUID,
        record_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Form per modificare scheda ICCD esistente."""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    # Get current user info
    user_query = select(User).where(User.id == current_user_id)
    user = await db.execute(user_query)
    current_user = user.scalar_one_or_none()
    
    # Recupera record ICCD dal database
    try:
        from app.models.iccd_records import ICCDBaseRecord
        
        record_query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == record_id,
                ICCDBaseRecord.site_id == site_id
            )
        )
        result = await db.execute(record_query)
        record = result.scalar_one_or_none()
        
        if not record:
            raise HTTPException(status_code=404, detail="Scheda ICCD non trovata")
        
        # Convert to dict for template
        record_data = {
            "id": str(record.id),
            "schema_type": record.schema_type,
            "nct": f"{record.nct_region}{record.nct_number}{record.nct_suffix or ''}",
            "iccd_data": record.iccd_data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading ICCD record {record_id} for edit: {e}")
        raise HTTPException(status_code=500, detail="Errore caricamento scheda ICCD")
    
    context = {
        "request": request,
        "site": site,
        "user_permission": permission,
        "current_user": current_user,
        "record": record_data,
        "record_id": str(record_id),
        "edit_mode": True,
        "can_read": permission.can_read(),
        "can_write": permission.can_write(),
        "can_admin": permission.can_admin()
    }
    
    return templates.TemplateResponse("sites/iccd_catalogation.html", context)
