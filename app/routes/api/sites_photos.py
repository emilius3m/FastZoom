# app/routes/api/sites_photos.py - Photo management API endpoints

from fastapi import APIRouter, Depends, Request, HTTPException, status, Form, File, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
import json

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.photos import Photo, PhotoType, MaterialType, ConservationStatus
from app.models.users import UserActivity
from app.routes.api.dependencies import get_site_access
from app.services.storage_service import storage_service
from app.services.photo_service import photo_metadata_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.storage_management_service import storage_management_service

photos_router = APIRouter()


@photos_router.get("/{site_id}/api/photos")
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


@photos_router.post("/{site_id}/api/photos/upload")
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
    """Upload foto al sito archeologico - FIXED: Background processing non bloccante"""
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

                logger.info(f"Photo record saved with ID: {photo_record.id}")

                # 7. Genera thumbnail DOPO che il record è stato salvato
                await file.seek(0)  # Reset file pointer per thumbnail
                thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                    file, str(photo_record.id)
                )

                if thumbnail_path:
                    photo_record.thumbnail_path = thumbnail_path
                    await db.commit()
                    logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
                else:
                    logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")

                logger.info(f"Photo {photo_record.id} saved with thumbnail_path: {photo_record.thumbnail_path}")
                
            except HTTPException as he:
                if he.status_code == 507:  # Storage full
                    logger.error(f"Storage full during upload of {file.filename}")
                    try:
                        cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=2000)
                        if cleanup_result['success']:
                            logger.info(f"Emergency cleanup successful: {cleanup_result['total_freed_mb']}MB freed")
                        else:
                            logger.error(f"Emergency cleanup failed: {cleanup_result}")
                    except Exception as cleanup_error:
                        logger.error(f"Cleanup attempt failed: {cleanup_error}")
                raise he
                
            except Exception as photo_error:
                logger.error(f"Error processing photo {file.filename}: {photo_error}")
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
        for photo_data in uploaded_photos:
            photo_id = photo_data["photo_id"]
            try:
                photo_query = select(Photo).where(Photo.id == UUID(photo_id))
                result = await db.execute(photo_query)
                photo_record = result.scalar_one_or_none()
                
                if not photo_record:
                    logger.warning(f"Photo record not found for deep zoom scheduling: {photo_id}")
                    continue

                try:
                    photo_content = await archaeological_minio_service.get_file(photo_record.file_path)
                    
                    from PIL import Image
                    import io
                    
                    with Image.open(io.BytesIO(photo_content)) as img:
                        width, height = img.size
                        max_dimension = max(width, height)
                        
                        if max_dimension > 2000:
                            logger.info(f"Scheduling deep zoom processing for large image {photo_id}: {width}x{height}")
                            
                            photo_record.deep_zoom_status = 'scheduled'
                            await db.commit()
                            
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

        return JSONResponse({
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "uploaded_photos": uploaded_photos
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        if 'filename' in locals():
            await storage_service.delete_file(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante upload: {str(e)}"
        )


@photos_router.get("/{site_id}/photos/{photo_id}/stream")
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

    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo or not photo.file_path.startswith('minio://'):
        raise HTTPException(status_code=404, detail="Foto non trovata")

    stream_url = await archaeological_minio_service.get_photo_stream_url(photo.file_path)

    if not stream_url:
        raise HTTPException(status_code=500, detail="Errore generazione URL")

    return RedirectResponse(url=stream_url, status_code=302)


@photos_router.get("/{site_id}/photos/{photo_id}/thumbnail")
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

    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    thumbnail_url = await archaeological_minio_service.get_thumbnail_url(str(photo_id))

    if not thumbnail_url:
        raise HTTPException(status_code=500, detail="Errore generazione URL thumbnail")

    return RedirectResponse(url=thumbnail_url, status_code=302)


@photos_router.get("/{site_id}/photos/{photo_id}/full")
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

    photo = await db.execute(
        select(Photo).where(
            and_(Photo.id == photo_id, Photo.site_id == site_id)
        )
    )
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    full_url = await archaeological_minio_service.get_photo_stream_url(photo.file_path)

    if not full_url:
        raise HTTPException(status_code=500, detail="Errore generazione URL immagine")

    return RedirectResponse(url=full_url, status_code=302)


@photos_router.get("/{site_id}/api/photos/search")
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


@photos_router.put("/{site_id}/photos/{photo_id}/update")
async def update_photo(
        site_id: UUID,
        photo_id: UUID,
        request: Request,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna metadati foto archeologica"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        update_data = await request.json()
        logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Received data: {update_data}")
    except Exception as e:
        logger.error(f"PUT /sites/{site_id}/photos/{photo_id}/update - JSON parsing error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")

    photo_query = select(Photo).where(
        and_(Photo.id == photo_id, Photo.site_id == site_id)
    )
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata nel sito")

    # Campi aggiornabili
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

    filtered_data = {}
    for field in updatable_fields:
        if field in update_data and update_data[field] is not None:
            value = update_data[field]

            if field in ['length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams', 'depth_level']:
                if value == '' or value == 'null' or value == 'None':
                    filtered_data[field] = None
                else:
                    try:
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
            raise HTTPException(status_code=400, detail=f"Tipo foto non valido: {filtered_data['photo_type']}")

    if 'material' in filtered_data and filtered_data['material']:
        try:
            filtered_data['material'] = MaterialType(filtered_data['material'])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Materiale non valido: {filtered_data['material']}")

    if 'conservation_status' in filtered_data and filtered_data['conservation_status']:
        try:
            filtered_data['conservation_status'] = ConservationStatus(filtered_data['conservation_status'])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Stato di conservazione non valido: {filtered_data['conservation_status']}")

    # Gestione date
    if 'find_date' in filtered_data and filtered_data['find_date']:
        try:
            if isinstance(filtered_data['find_date'], str):
                if filtered_data['find_date'] == '' or filtered_data['find_date'] == 'null' or filtered_data['find_date'] == 'None':
                    filtered_data['find_date'] = None
                else:
                    try:
                        filtered_data['find_date'] = datetime.fromisoformat(filtered_data['find_date'])
                    except ValueError:
                        try:
                            filtered_data['find_date'] = datetime.strptime(filtered_data['find_date'], '%Y-%m-%d')
                        except ValueError:
                            raise HTTPException(status_code=400, detail="Formato data non valido per find_date")
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato data non valido per find_date")

    # Gestione JSON fields
    if 'keywords' in filtered_data:
        if isinstance(filtered_data['keywords'], str) and filtered_data['keywords']:
            keywords_list = [kw.strip() for kw in filtered_data['keywords'].split(',') if kw.strip()]
            filtered_data['keywords'] = json.dumps(keywords_list)
        elif isinstance(filtered_data['keywords'], list):
            filtered_data['keywords'] = json.dumps(filtered_data['keywords'])
        elif not filtered_data['keywords']:
            filtered_data['keywords'] = None

    if 'external_links' in filtered_data and isinstance(filtered_data['external_links'], list):
        filtered_data['external_links'] = json.dumps(filtered_data['external_links'])

    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Filtered data to apply: {filtered_data}")
    
    for field, value in filtered_data.items():
        old_value = getattr(photo, field, None)
        if value == '' or value == 'null' or value == 'None':
            setattr(photo, field, None)
            logger.info(f"PUT - Field '{field}': '{old_value}' -> None")
        else:
            setattr(photo, field, value)
            logger.info(f"PUT - Field '{field}': '{old_value}' -> '{value}'")

    photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Photo updated timestamp: {photo.updated}")

    # Log activity
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
    
    response_data = {
        "message": "Foto aggiornata con successo",
        "photo_id": str(photo_id),
        "updated_fields": list(filtered_data.keys()),
        "photo_data": photo.to_dict()
    }
    
    logger.info(f"PUT /sites/{site_id}/photos/{photo_id}/update - Response: {response_data}")
    return response_data


@photos_router.delete("/{site_id}/photos/{photo_id}")
async def delete_photo(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_async_session)
):
    """Elimina foto dal sito archeologico"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    photo_query = select(Photo).where(
        and_(Photo.id == photo_id, Photo.site_id == site_id)
    )
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata nel sito")

    try:
        photo_filename = photo.filename
        photo_path = photo.file_path
        thumbnail_path = photo.thumbnail_path

        await db.delete(photo)
        await db.commit()

        try:
            if photo_path:
                if '/' in photo_path:
                    try:
                        success = await archaeological_minio_service.remove_file(photo_path)
                        if success:
                            logger.info(f"File eliminato da Archaeological MinIO: {photo_path}")
                        else:
                            logger.warning(f"Impossibile eliminare file: {photo_path}")
                    except Exception as e:
                        logger.warning(f"Errore eliminazione file Archaeological MinIO {photo_path}: {e}")
                elif photo_path.startswith("storage/") or photo_path.startswith("app/static/uploads/"):
                    file_path = Path(photo_path)
                    if file_path.exists():
                        file_path.unlink()
                        logger.info(f"File locale eliminato: {file_path}")

            if thumbnail_path:
                if thumbnail_path.startswith("thumbnails/"):
                    try:
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
                    thumbnail_file_path = Path(thumbnail_path)
                    if thumbnail_file_path.exists():
                        thumbnail_file_path.unlink()
                        logger.info(f"Thumbnail locale eliminato: {thumbnail_file_path}")

        except Exception as e:
            logger.warning(f"Errore durante eliminazione file fisici: {e}")

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


@photos_router.post("/{site_id}/api/photos/bulk-delete")
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

    photo_ids_raw = delete_data.get("photo_ids", [])
    if not photo_ids_raw:
        raise HTTPException(status_code=400, detail="Nessuna foto selezionata")

    try:
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
                photo_filename = photo.filename
                photo_path = photo.file_path
                thumbnail_path = photo.thumbnail_path

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

                await db.delete(photo)
                deleted_count += 1

                activity = UserActivity(
                    user_id=current_user_id,
                    site_id=site_id,
                    activity_type="DELETE",
                    activity_desc=f"Eliminazione massiva foto {photo_filename}",
                    extra_data=json.dumps({
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


@photos_router.post("/{site_id}/api/photos/bulk-update")
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

    photo_ids_raw = update_data.get("photo_ids", [])
    metadata = update_data.get("metadata", {})
    
    add_tags = update_data.get("add_tags", [])
    remove_tags = update_data.get("remove_tags", [])

    if not photo_ids_raw:
        raise HTTPException(status_code=400, detail="Nessuna foto selezionata")

    logger.info(f"Bulk update received data: {update_data}")

    try:
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

        photos_query = select(Photo).where(and_(
            Photo.site_id == site_id,
            Photo.id.in_(photo_ids)
        ))
        photos = await db.execute(photos_query)
        photos = photos.scalars().all()

        if not photos:
            raise HTTPException(status_code=404, detail="Nessuna foto trovata con gli ID specificati")

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

        filtered_metadata = {}
        for field in updatable_fields:
            if field in metadata and metadata[field] is not None and metadata[field] != '':
                value = metadata[field]
                
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
                raise HTTPException(status_code=400, detail=f"Tipo foto non valido: {filtered_metadata['photo_type']}")

        if 'material' in filtered_metadata and filtered_metadata['material']:
            try:
                filtered_metadata['material'] = MaterialType(filtered_metadata['material'])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Materiale non valido: {filtered_metadata['material']}")

        if 'conservation_status' in filtered_metadata and filtered_metadata['conservation_status']:
            try:
                filtered_metadata['conservation_status'] = ConservationStatus(filtered_metadata['conservation_status'])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Stato di conservazione non valido: {filtered_metadata['conservation_status']}")

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
                            raise HTTPException(status_code=400, detail="Formato data non valido per find_date")
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato data non valido per find_date")

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
                for field, value in filtered_metadata.items():
                    old_value = getattr(photo, field, None)
                    setattr(photo, field, value)
                    if field not in updated_fields:
                        updated_fields.append(field)
                    logger.info(f"Bulk update - Photo {photo.id} - Field '{field}': '{old_value}' -> '{value}'")

                if add_tags or remove_tags:
                    current_tags = getattr(photo, 'tags', None) or []
                    if isinstance(current_tags, str):
                        try:
                            current_tags = json.loads(current_tags)
                        except:
                            current_tags = []

                    for tag in add_tags:
                        if tag not in current_tags:
                            current_tags.append(tag)

                    for tag in remove_tags:
                        if tag in current_tags:
                            current_tags.remove(tag)

                    if hasattr(photo, 'tags'):
                        photo.tags = current_tags
                        if 'tags' not in updated_fields:
                            updated_fields.append('tags')

                photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
                updated_count += 1

            except Exception as e:
                logger.warning(f"Error updating photo {photo.id}: {e}")
                continue

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


async def log_user_activity(
        db: AsyncSession,
        user_id: UUID,
        site_id: UUID,
        activity_type: str,
        activity_desc: str,
        extra_data: str = None
):
    """Log attività utente nel sistema"""
    try:
        activity = UserActivity(
            user_id=user_id,
            site_id=site_id,
            activity_type=activity_type,
            activity_desc=activity_desc,
            extra_data=extra_data
        )

        db.add(activity)
        await db.commit()
        logger.info(f"Activity logged: {activity_type} by {user_id}")

    except Exception as e:
        logger.error(f"Error logging activity: {e}")
        await db.rollback()