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
import asyncio

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.models import UserActivity
from app.routes.api.dependencies import get_site_access
from app.services.storage_service import storage_service
from app.services.photo_service import photo_metadata_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.storage_management_service import storage_management_service
from app.services.photo_serving_service import photo_serving_service

photos_router = APIRouter()


@photos_router.get("/site/{site_id}/photos")
async def get_site_photos_api(
        site_id: UUID,
        # Basic filters
        search: str = None,
        photo_type: str = None,
        
        # Archaeological filters
        material: str = None,
        conservation_status: str = None,
        excavation_area: str = None,
        stratigraphic_unit: str = None,
        chronology_period: str = None,
        object_type: str = None,
        
        # Status filters
        is_published: bool = None,
        is_validated: bool = None,
        has_deep_zoom: bool = None,
        
        # Date filters
        upload_date_from: str = None,
        upload_date_to: str = None,
        photo_date_from: str = None,
        photo_date_to: str = None,
        find_date_from: str = None,
        find_date_to: str = None,
        
        # Dimension filters
        min_width: int = None,
        max_width: int = None,
        min_height: int = None,
        max_height: int = None,
        min_file_size_mb: float = None,
        max_file_size_mb: float = None,
        
        # Metadata presence filters
        has_inventory: bool = None,
        has_description: bool = None,
        has_photographer: bool = None,
        
        # Sorting
        sort_by: str = "created_desc",
        
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """
    API avanzata per ottenere foto del sito con filtri archeologici completi
    
    Filtri disponibili:
    - Basic: search, photo_type
    - Archaeological: material, conservation_status, excavation_area, chronology_period
    - Status: is_published, is_validated, has_deep_zoom
    - Date ranges: upload_date, photo_date, find_date
    - Dimensions: width, height, file_size
    - Metadata presence: has_inventory, has_description, has_photographer
    """
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # Base query
    photos_query = select(Photo).where(Photo.site_id == site_id)

    # Apply filters
    if search:
        search_term = f"%{search}%"
        photos_query = photos_query.where(
            or_(
                Photo.filename.ilike(search_term),
                Photo.title.ilike(search_term),
                Photo.description.ilike(search_term),
                Photo.inventory_number.ilike(search_term),
                Photo.keywords.ilike(search_term)
            )
        )

    if photo_type:
        try:
            photos_query = photos_query.where(Photo.photo_type == PhotoType(photo_type))
        except ValueError:
            pass

    if material:
        try:
            photos_query = photos_query.where(Photo.material == MaterialType(material))
        except ValueError:
            pass

    if conservation_status:
        try:
            photos_query = photos_query.where(Photo.conservation_status == ConservationStatus(conservation_status))
        except ValueError:
            pass

    if excavation_area:
        photos_query = photos_query.where(Photo.excavation_area.ilike(f"%{excavation_area}%"))

    if stratigraphic_unit:
        photos_query = photos_query.where(Photo.stratigraphic_unit.ilike(f"%{stratigraphic_unit}%"))

    if chronology_period:
        photos_query = photos_query.where(Photo.chronology_period.ilike(f"%{chronology_period}%"))

    if object_type:
        photos_query = photos_query.where(Photo.object_type.ilike(f"%{object_type}%"))

    # Status filters
    if is_published is not None:
        photos_query = photos_query.where(Photo.is_published == is_published)

    if is_validated is not None:
        photos_query = photos_query.where(Photo.is_validated == is_validated)

    if has_deep_zoom is not None:
        photos_query = photos_query.where(Photo.has_deep_zoom == has_deep_zoom)

    # Date range filters
    if upload_date_from:
        try:
            date_from = datetime.fromisoformat(upload_date_from)
            photos_query = photos_query.where(Photo.created_at >= date_from)
        except ValueError:
            pass

    if upload_date_to:
        try:
            date_to = datetime.fromisoformat(upload_date_to)
            photos_query = photos_query.where(Photo.created_at <= date_to)
        except ValueError:
            pass

    if photo_date_from:
        try:
            date_from = datetime.fromisoformat(photo_date_from)
            photos_query = photos_query.where(Photo.photo_date >= date_from)
        except ValueError:
            pass

    if photo_date_to:
        try:
            date_to = datetime.fromisoformat(photo_date_to)
            photos_query = photos_query.where(Photo.photo_date <= date_to)
        except ValueError:
            pass

    if find_date_from:
        try:
            date_from = datetime.fromisoformat(find_date_from)
            photos_query = photos_query.where(Photo.find_date >= date_from)
        except ValueError:
            pass

    if find_date_to:
        try:
            date_to = datetime.fromisoformat(find_date_to)
            photos_query = photos_query.where(Photo.find_date <= date_to)
        except ValueError:
            pass

    # Dimension filters
    if min_width:
        photos_query = photos_query.where(Photo.width >= min_width)

    if max_width:
        photos_query = photos_query.where(Photo.width <= max_width)

    if min_height:
        photos_query = photos_query.where(Photo.height >= min_height)

    if max_height:
        photos_query = photos_query.where(Photo.height <= max_height)

    if min_file_size_mb:
        photos_query = photos_query.where(Photo.file_size >= int(min_file_size_mb * 1024 * 1024))

    if max_file_size_mb:
        photos_query = photos_query.where(Photo.file_size <= int(max_file_size_mb * 1024 * 1024))

    # Metadata presence filters
    if has_inventory:
        if has_inventory:
            photos_query = photos_query.where(Photo.inventory_number.isnot(None))
        else:
            photos_query = photos_query.where(Photo.inventory_number.is_(None))

    if has_description:
        if has_description:
            photos_query = photos_query.where(Photo.description.isnot(None))
        else:
            photos_query = photos_query.where(Photo.description.is_(None))

    if has_photographer:
        if has_photographer:
            photos_query = photos_query.where(Photo.photographer.isnot(None))
        else:
            photos_query = photos_query.where(Photo.photographer.is_(None))

    # Sorting
    sort_mapping = {
        "created_desc": Photo.created_at.desc(),
        "created_asc": Photo.created_at.asc(),
        "filename_asc": Photo.filename.asc(),
        "filename_desc": Photo.filename.desc(),
        "size_desc": Photo.file_size.desc(),
        "size_asc": Photo.file_size.asc(),
        "photo_date_desc": Photo.photo_date.desc().nullslast(),
        "photo_date_asc": Photo.photo_date.asc().nullslast(),
        "inventory_asc": Photo.inventory_number.asc().nullslast(),
        "inventory_desc": Photo.inventory_number.desc().nullslast(),
        "material_asc": Photo.material.asc().nullslast(),
        "find_date_desc": Photo.find_date.desc().nullslast(),
    }
    
    if sort_by in sort_mapping:
        photos_query = photos_query.order_by(sort_mapping[sort_by])
    else:
        photos_query = photos_query.order_by(Photo.created_at.desc())

    # Execute query
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    # Convert to dictionary format with proper URLs
    photos_data = []
    for photo in photos:
        photo_dict = photo.to_dict()
        photo_dict['file_url'] = f"/photos/{photo.id}/full"
        photo_dict['thumbnail_url'] = f"/photos/{photo.id}/thumbnail"
        # Add tags property for compatibility
        photo_dict['tags'] = photo.get_keywords_list()
        photos_data.append(photo_dict)

    logger.info(f"Photos API: Returned {len(photos_data)} photos with filters: "
                f"search={search}, photo_type={photo_type}, material={material}, "
                f"conservation_status={conservation_status}, sort_by={sort_by}")

    return JSONResponse(photos_data)


@photos_router.post("/site/{site_id}/photos/upload")
async def upload_photo(
        site_id: UUID,
        photos: List[UploadFile] = File(...),
        # Basic metadata
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        photo_type: Optional[str] = Form(None),
        photographer: Optional[str] = Form(None),
        keywords: Optional[str] = Form(None),
        
        # Archaeological metadata
        inventory_number: Optional[str] = Form(None),
        catalog_number: Optional[str] = Form(None),
        excavation_area: Optional[str] = Form(None),
        stratigraphic_unit: Optional[str] = Form(None),
        grid_square: Optional[str] = Form(None),
        depth_level: Optional[float] = Form(None),
        find_date: Optional[str] = Form(None),
        finder: Optional[str] = Form(None),
        excavation_campaign: Optional[str] = Form(None),
        
        # Material and object
        material: Optional[str] = Form(None),
        material_details: Optional[str] = Form(None),
        object_type: Optional[str] = Form(None),
        object_function: Optional[str] = Form(None),
        
        # Dimensions
        length_cm: Optional[float] = Form(None),
        width_cm: Optional[float] = Form(None),
        height_cm: Optional[float] = Form(None),
        diameter_cm: Optional[float] = Form(None),
        weight_grams: Optional[float] = Form(None),
        
        # Chronology
        chronology_period: Optional[str] = Form(None),
        chronology_culture: Optional[str] = Form(None),
        dating_from: Optional[str] = Form(None),
        dating_to: Optional[str] = Form(None),
        dating_notes: Optional[str] = Form(None),
        
        # Conservation
        conservation_status: Optional[str] = Form(None),
        conservation_notes: Optional[str] = Form(None),
        restoration_history: Optional[str] = Form(None),
        
        # References
        bibliography: Optional[str] = Form(None),
        comparative_references: Optional[str] = Form(None),
        external_links: Optional[str] = Form(None),
        
        # Rights
        copyright_holder: Optional[str] = Form(None),
        license_type: Optional[str] = Form(None),
        usage_rights: Optional[str] = Form(None),
        
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

                # 4. Prepara TUTTI i metadati archeologici da form utente
                archaeological_metadata_from_form = {}
                
                # Basic metadata
                if title:
                    archaeological_metadata_from_form['title'] = title
                if description:
                    archaeological_metadata_from_form['description'] = description
                if photographer:
                    archaeological_metadata_from_form['photographer'] = photographer
                if keywords:
                    archaeological_metadata_from_form['keywords'] = keywords
                if photo_type:
                    archaeological_metadata_from_form['photo_type'] = photo_type
                
                # Archaeological context
                if inventory_number:
                    archaeological_metadata_from_form['inventory_number'] = inventory_number
                if catalog_number:
                    archaeological_metadata_from_form['catalog_number'] = catalog_number
                if excavation_area:
                    archaeological_metadata_from_form['excavation_area'] = excavation_area
                if stratigraphic_unit:
                    archaeological_metadata_from_form['stratigraphic_unit'] = stratigraphic_unit
                if grid_square:
                    archaeological_metadata_from_form['grid_square'] = grid_square
                if depth_level is not None:
                    archaeological_metadata_from_form['depth_level'] = depth_level
                if find_date:
                    try:
                        archaeological_metadata_from_form['find_date'] = datetime.fromisoformat(find_date.replace('Z', '+00:00'))
                    except ValueError:
                        try:
                            archaeological_metadata_from_form['find_date'] = datetime.strptime(find_date, '%Y-%m-%d')
                        except ValueError:
                            logger.warning(f"Invalid find_date format: {find_date}")
                if finder:
                    archaeological_metadata_from_form['finder'] = finder
                if excavation_campaign:
                    archaeological_metadata_from_form['excavation_campaign'] = excavation_campaign
                
                # Material and object
                if material:
                    archaeological_metadata_from_form['material'] = material
                if material_details:
                    archaeological_metadata_from_form['material_details'] = material_details
                if object_type:
                    archaeological_metadata_from_form['object_type'] = object_type
                if object_function:
                    archaeological_metadata_from_form['object_function'] = object_function
                
                # Dimensions
                if length_cm is not None:
                    archaeological_metadata_from_form['length_cm'] = length_cm
                if width_cm is not None:
                    archaeological_metadata_from_form['width_cm'] = width_cm
                if height_cm is not None:
                    archaeological_metadata_from_form['height_cm'] = height_cm
                if diameter_cm is not None:
                    archaeological_metadata_from_form['diameter_cm'] = diameter_cm
                if weight_grams is not None:
                    archaeological_metadata_from_form['weight_grams'] = weight_grams
                
                # Chronology
                if chronology_period:
                    archaeological_metadata_from_form['chronology_period'] = chronology_period
                if chronology_culture:
                    archaeological_metadata_from_form['chronology_culture'] = chronology_culture
                if dating_from:
                    archaeological_metadata_from_form['dating_from'] = dating_from
                if dating_to:
                    archaeological_metadata_from_form['dating_to'] = dating_to
                if dating_notes:
                    archaeological_metadata_from_form['dating_notes'] = dating_notes
                
                # Conservation
                if conservation_status:
                    archaeological_metadata_from_form['conservation_status'] = conservation_status
                if conservation_notes:
                    archaeological_metadata_from_form['conservation_notes'] = conservation_notes
                if restoration_history:
                    archaeological_metadata_from_form['restoration_history'] = restoration_history
                
                # References
                if bibliography:
                    archaeological_metadata_from_form['bibliography'] = bibliography
                if comparative_references:
                    archaeological_metadata_from_form['comparative_references'] = comparative_references
                if external_links:
                    archaeological_metadata_from_form['external_links'] = external_links
                
                # Rights
                if copyright_holder:
                    archaeological_metadata_from_form['copyright_holder'] = copyright_holder
                if license_type:
                    archaeological_metadata_from_form['license_type'] = license_type
                if usage_rights:
                    archaeological_metadata_from_form['usage_rights'] = usage_rights
                
                logger.info(f"📋 Complete metadata for {file.filename}: {list(archaeological_metadata_from_form.keys())}")
                
                # 5. Crea record nel database CON metadati archeologici
                photo_record = await photo_metadata_service.create_photo_record(
                    filename=filename,
                    original_filename=file.filename,
                    file_path=file_path,
                    file_size=file_size,
                    site_id=str(site_id),
                    uploaded_by=str(current_user_id),
                    metadata=metadata,
                    archaeological_metadata=archaeological_metadata_from_form
                )

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

        # 8. COMPLETAMENTE RIVISTO: Prepara lista foto per tiles MA NON inizia processing
        # Il processing inizierà DOPO che tutte le foto sono state caricate
        photos_needing_tiles = []
        
        for photo_data in uploaded_photos:
            photo_id = photo_data["photo_id"]
            try:
                # Use already extracted dimensions from metadata
                width = photo_data.get("metadata", {}).get("width", 0)
                height = photo_data.get("metadata", {}).get("height", 0)
                max_dimension = max(width, height) if width and height else 0
                
                if max_dimension > 2000:
                    logger.info(f"📋 Photo {photo_id} needs tiles: {width}x{height}")
                    
                    # Update status in database to 'scheduled' (but don't start yet)
                    photo_query = select(Photo).where(Photo.id == UUID(photo_id))
                    result = await db.execute(photo_query)
                    photo_record = result.scalar_one_or_none()
                    
                    if photo_record:
                        photo_record.deep_zoom_status = 'scheduled'
                        await db.commit()
                        
                        photos_needing_tiles.append({
                            'photo_id': photo_id,
                            'file_path': photo_record.file_path,
                            'width': width,
                            'height': height,
                            'archaeological_metadata': {
                                'inventory_number': photo_record.inventory_number,
                                'excavation_area': photo_record.excavation_area,
                                'material': photo_record.material.value if photo_record.material else None,
                                'chronology_period': photo_record.chronology_period,
                                'photo_type': photo_record.photo_type.value if photo_record.photo_type else None,
                                'photographer': photo_record.photographer,
                                'description': photo_record.description,
                                'keywords': photo_record.keywords
                            }
                        })
                else:
                    logger.info(f"Skipping tiles for small image {photo_id}: {width}x{height}")

            except Exception as e:
                logger.error(f"❌ Error checking tile requirements for photo {photo_id}: {e}")
        
        # 9. DOPO tutti gli upload: avvia UNICO task background per processare TUTTE le foto sequenzialmente
        if photos_needing_tiles:
            logger.info(f"🎯 {len(photos_needing_tiles)} foto richiedono tiles - avvio batch processing in background")
            
            # Avvia UN SOLO task che processerà tutte le foto una alla volta
            asyncio.create_task(
                deep_zoom_minio_service.process_tiles_batch_sequential(
                    photos_list=photos_needing_tiles,
                    site_id=str(site_id)
                )
            )
            
            logger.info(f"✅ Batch tiles processing schedulato per {len(photos_needing_tiles)} foto")

        # Ritorna risposta con info foto E ID per batch processing
        response_data = {
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "uploaded_photos": uploaded_photos,
            "total_uploaded": len(uploaded_photos),
            "photos_needing_tiles": len(photos_needing_tiles)
        }
        
        logger.info(f"✅ Upload API response: {len(uploaded_photos)} foto caricate, {len(photos_needing_tiles)} necessitano tiles")
        
        return JSONResponse(response_data)

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


@photos_router.get("/site/{site_id}/photos/{photo_id}/stream")
async def stream_photo_from_minio(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Stream foto - CONSOLIDATED"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Use consolidated photo serving service for consistent behavior
    return await photo_serving_service.serve_photo_full(photo_id, db)


@photos_router.get("/site/{site_id}/photos/{photo_id}/thumbnail")
async def get_photo_thumbnail(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni thumbnail foto - CONSOLIDATED"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Use consolidated photo serving service
    return await photo_serving_service.serve_photo_thumbnail(photo_id, db)


@photos_router.get("/site/{site_id}/photos/{photo_id}/full")
async def get_photo_full(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access),
        db: AsyncSession = Depends(get_async_session)
):
    """Ottieni immagine completa foto - CONSOLIDATED"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi richiesti")

    # Use consolidated photo serving service
    return await photo_serving_service.serve_photo_full(photo_id, db)


@photos_router.get("/site/{site_id}/api/photos/search")
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


@photos_router.put("/site/{site_id}/photos/{photo_id}/update")
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
        logger.info(f"PUT /site/{site_id}/photos/{photo_id}/update - Received data: {update_data}")
    except Exception as e:
        logger.error(f"PUT /site/{site_id}/photos/{photo_id}/update - JSON parsing error: {str(e)}")
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
        'inventory_number', 'catalog_number',
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

    logger.info(f"PUT /site/{site_id}/photos/{photo_id}/update - Filtered data to apply: {filtered_data}")
    
    for field, value in filtered_data.items():
        old_value = getattr(photo, field, None)
        if value == '' or value == 'null' or value == 'None':
            setattr(photo, field, None)
            logger.info(f"PUT - Field '{field}': '{old_value}' -> None")
        else:
            setattr(photo, field, value)
            logger.info(f"PUT - Field '{field}': '{old_value}' -> '{value}'")

    photo.updated = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info(f"PUT /site/{site_id}/photos/{photo_id}/update - Photo updated timestamp: {photo.updated}")

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
    

    logger.info(f"PUT /site/{site_id}/photos/{photo_id}/update - Updated fields: {list(filtered_data.keys())}")

    # Broadcast WebSocket notification for photo update
    try:
        from app.routes.api.notifications_ws import notification_manager
        await notification_manager.broadcast_photo_updated(
            site_id=str(site_id),
            photo_id=str(photo_id),
            updated_fields=list(filtered_data.keys()),
            photo_filename=photo.filename,
            user_id=str(current_user_id)
        )
        logger.info(f"WebSocket notification sent for photo update: {photo_id}")
    except Exception as ws_error:
        logger.warning(f"Failed to send WebSocket notification for photo update: {ws_error}")
        # Don't fail the update if WebSocket notification fails

    response_data = {
        "message": "Foto aggiornata con successo",
        "photo_id": str(photo_id),
        "updated_fields": list(filtered_data.keys()),
        "photo_data": photo.to_dict()
    }

    logger.info(f"PUT /site/{site_id}/photos/{photo_id}/update - Response: {response_data}")
    return response_data


@photos_router.delete("/site/{site_id}/photos/{photo_id}")
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


@photos_router.post("/site/{site_id}/photos/bulk-delete")
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


@photos_router.post("/site/{site_id}/photos/bulk-update")
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
            'inventory_number', 'catalog_number',
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