# app/routes/api/sites_photos.py - Photo management API endpoints

from fastapi import APIRouter, Depends, Request, HTTPException, status, Form, File, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
import json
import asyncio

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.models import UserActivity
from app.models import USFile
from app.routes.api.dependencies import get_site_access
from app.services.storage_service import storage_service
from app.services.photo_service import photo_metadata_service
from app.services.archaeological_minio_service import archaeological_minio_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service
from app.services.deep_zoom_background_service import deep_zoom_background_service
from app.services.storage_management_service import storage_management_service
from app.services.photo_serving_service import photo_serving_service

photos_router = APIRouter()


@photos_router.get("/site/{site_id}/photos")
async def get_site_photos_api(
        site_id: str,  # Changed from UUID to str to handle both formats
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
        current_user_id: UUID = Depends(get_current_user_id),
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
    
    # Use centralized normalization function
    try:
        from app.routes.api.dependencies import get_normalized_site_id
        normalized_site_id = await get_normalized_site_id(site_id, current_user_id, db)
    except:
        # Fallback to manual normalization if dependency fails
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            raise HTTPException(status_code=404, detail="ID sito non valido")
        
        # Quick validation without full site access check for performance
        site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == normalized_site_id)
        site = await db.execute(site_query)
        site = site.scalar_one_or_none()
        
        if not site:
            raise HTTP_exception(status_code=404, detail="Sito archeologico non trovato")
        
        # Try basic permission check
        from app.routes.api.dependencies import get_site_access_by_id
        site, permission = await get_site_access_by_id(UUID(normalized_site_id), current_user_id, db)

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi insufficienti")

    # === Query 1: General photos from Photo table ===
    photos_query = select(Photo).where(Photo.site_id == normalized_site_id)

    # Apply filters to Photo query
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

    # Execute Photo query
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()

    # === Query 2: US photos from USFile table ===
    from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria, us_files_association, usm_files_association
    
    us_files_query = select(USFile).where(
        and_(
            USFile.site_id == normalized_site_id,
            USFile.file_category == 'fotografia'
        )
    )

    # Apply search filter to USFile query
    if search:
        search_term = f"%{search}%"
        us_files_query = us_files_query.where(
            or_(
                USFile.filename.ilike(search_term),
                USFile.title.ilike(search_term),
                USFile.description.ilike(search_term),
                USFile.original_filename.ilike(search_term)
            )
        )

    # Execute USFile query
    us_files = await db.execute(us_files_query)
    us_files = us_files.scalars().all()
    
    # Build a map of file_id -> US/USM codes for efficient lookup
    us_file_ids = [uf.id for uf in us_files]
    us_associations_map = {}  # {file_id: [list of US codes]}
    
    if us_file_ids:
        # Query US associations
        us_assoc_query = select(us_files_association.c.file_id, us_files_association.c.us_id).where(
            us_files_association.c.file_id.in_(us_file_ids)
        )
        us_assoc_results = await db.execute(us_assoc_query)
        us_assoc_list = us_assoc_results.fetchall()
        
        # Get US codes for these associations
        if us_assoc_list:
            us_ids = [row.us_id for row in us_assoc_list]
            us_query = select(UnitaStratigrafica.id, UnitaStratigrafica.us_code).where(
                UnitaStratigrafica.id.in_(us_ids)
            )
            us_results = await db.execute(us_query)
            us_codes_map = {row.id: row.us_code for row in us_results.fetchall()}
            
            # Build associations map
            for assoc in us_assoc_list:
                file_id = assoc.file_id
                us_code = us_codes_map.get(assoc.us_id)
                if us_code:
                    if file_id not in us_associations_map:
                        us_associations_map[file_id] = []
                    us_associations_map[file_id].append(f"US {us_code}")
        
        # Query USM associations
        usm_assoc_query = select(usm_files_association.c.file_id, usm_files_association.c.usm_id).where(
            usm_files_association.c.file_id.in_(us_file_ids)
        )
        usm_assoc_results = await db.execute(usm_assoc_query)
        usm_assoc_list = usm_assoc_results.fetchall()
        
        # Get USM codes for these associations
        if usm_assoc_list:
            usm_ids = [row.usm_id for row in usm_assoc_list]
            usm_query = select(UnitaStratigraficaMuraria.id, UnitaStratigraficaMuraria.usm_code).where(
                UnitaStratigraficaMuraria.id.in_(usm_ids)
            )
            usm_results = await db.execute(usm_query)
            usm_codes_map = {row.id: row.usm_code for row in usm_results.fetchall()}
            
            # Build associations map
            for assoc in usm_assoc_list:
                file_id = assoc.file_id
                usm_code = usm_codes_map.get(assoc.usm_id)
                if usm_code:
                    if file_id not in us_associations_map:
                        us_associations_map[file_id] = []
                    us_associations_map[file_id].append(f"USM {usm_code}")

    # === Convert to unified dictionary format ===
    photos_data = []
    
    # Add general photos
    for photo in photos:
        photo_dict = photo.to_dict()
        photo_dict['file_url'] = f"/photos/{photo.id}/full"
        photo_dict['thumbnail_url'] = f"/photos/{photo.id}/thumbnail"
        photo_dict['tags'] = photo.get_keywords_list()
        photo_dict['source_type'] = 'photo'  # Mark as general photo
        photos_data.append(photo_dict)

    # Add US photos with unified format
    for us_file in us_files:
        # Get US/USM codes this file belongs to
        us_codes = us_associations_map.get(us_file.id, [])
        us_codes_string = ", ".join(us_codes) if us_codes else None
        
        us_photo_dict = {
            # ID and relations
            "id": str(us_file.id),
            "site_id": str(us_file.site_id),
            "uploaded_by": str(us_file.uploaded_by),
            
            # File info
            "filename": us_file.filename,
            "original_filename": us_file.original_filename,
            "filepath": us_file.filepath,
            "file_size": us_file.filesize,
            "mime_type": us_file.mimetype,
            
            # Image metadata
            "width": us_file.width,
            "height": us_file.height,
            "format": None,  # Not stored in USFile
            "color_space": None,
            "color_profile": None,
            
            # Photo metadata
            "title": us_file.title,
            "description": us_file.description,
            "keywords": None,
            "photo_type": "us_fotografia",  # Special type for US photos
            "photo_type_display": "US Fotografia",
            
            # Camera/EXIF data
            "camera_make": None,
            "camera_model": us_file.camera_info,
            "lens_info": None,
            "iso": None,
            "aperture": None,
            "shutter_speed": None,
            "focal_length": None,
            
            # Localization
            "us_reference": None,
            "usm_reference": None,
            "tomba_reference": None,
            "reperto_reference": None,
            "gps_lat": None,
            "gps_lng": None,
            "gps_altitude": None,
            "has_coordinates": False,
            
            # Archaeological metadata (limited for US files)
            "inventory_number": None,
            "catalog_number": None,
            "excavation_area": None,
            "stratigraphic_unit": us_codes_string,  # Include US/USM codes here
            "grid_square": None,
            "depth_level": None,
            "find_date": us_file.photo_date.isoformat() if us_file.photo_date else None,
            "finder": None,
            "excavation_campaign": None,
            "material": None,
            "material_details": None,
            "object_type": None,
            "object_function": None,
            "length_cm": None,
            "width_cm": None,
            "height_cm": None,
            "diameter_cm": None,
            "weight_grams": None,
            "chronology_period": None,
            "chronology_culture": None,
            "dating_from": None,
            "dating_to": None,
            "dating_notes": None,
            "conservation_status": None,
            "conservation_notes": None,
            "restoration_history": None,
            "bibliography": None,
            "comparative_references": None,
            "external_links": None,
            "copyright_holder": None,
            "license_type": None,
            "usage_rights": None,
            "is_published": us_file.is_published,
            "is_validated": us_file.is_validated,
            "validation_notes": None,
            
            # Deep zoom
            "has_deep_zoom": us_file.is_deepzoom_enabled,
            "deepzoom_status": us_file.deepzoom_status,
            "deepzoom_processed_at": None,
            "tile_count": 0,
            "max_zoom_level": 0,
            "is_deepzoom_ready": us_file.deepzoom_status == 'completed',
            
            # Management
            "photographer": us_file.photographer,
            "photo_date": us_file.photo_date.isoformat() if us_file.photo_date else None,
            "is_featured": False,
            "is_public": True,
            "sort_order": 0,
            
            # Timestamps
            "created_at": us_file.created_at.isoformat() if us_file.created_at else None,
            "updated_at": us_file.updated_at.isoformat() if us_file.updated_at else None,
            
            # URLs (using USFile serving endpoints)
            "thumbnail_url": f"/api/us-files/{us_file.id}/thumbnail",
            "full_url": f"/api/us-files/{us_file.id}/view",
            "file_url": f"/api/us-files/{us_file.id}/view",
            "download_url": f"/api/us-files/{us_file.id}/download",
            
            # Source marker
            "source_type": "us_file",  # Mark as US photo
            "upload_date": us_file.created_at.isoformat() if us_file.created_at else None,
            "tags": []  # US files don't have tags
        }
        photos_data.append(us_photo_dict)

    logger.info(f"Photos API: Returned {len(photos)} general photos + {len(us_files)} US photos = {len(photos_data)} total with filters: "
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
        # Queue control
        use_queue: Optional[bool] = Form(False),
        priority: Optional[str] = Form("normal"),
        
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
    """Upload foto al sito archeologico - ASYNC PARALLEL PROCESSING con Request Queueing"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Check if we should use queue based on system load or explicit request
    from app.services.request_queue_service import request_queue_service, RequestPriority
    from app.core.config import get_settings
    settings = get_settings()
    
    should_queue = use_queue or (
        settings.queue_enabled and
        (request_queue_service.system_monitor.is_system_overloaded() or
         request_queue_service.system_monitor.get_load_factor() > 0.6)
    )
    
    if should_queue:
        return await _handle_queued_upload(
            site_id, photos, title, description, photo_type, photographer, keywords,
            inventory_number, catalog_number, excavation_area, stratigraphic_unit,
            grid_square, depth_level, find_date, finder, excavation_campaign,
            material, material_details, object_type, object_function,
            length_cm, width_cm, height_cm, diameter_cm, weight_grams,
            chronology_period, chronology_culture, dating_from, dating_to, dating_notes,
            conservation_status, conservation_notes, restoration_history,
            bibliography, comparative_references, external_links,
            copyright_holder, license_type, usage_rights,
            site_access, current_user_id, db, priority
        )

    try:
        # Ensure MinIO buckets exist before uploading
        try:
            await storage_management_service.ensure_buckets_exist()
        except Exception as storage_error:
            logger.error(f"Storage service initialization failed: {storage_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service is currently unavailable. Please try again later."
            )
        
        # Check storage health before uploading
        try:
            storage_usage = await storage_management_service.get_storage_usage()
            if storage_usage.get('total_size_gb', 0) > 8:  # >80% of 10GB
                logger.warning(f"Storage usage critical ({storage_usage.get('total_size_gb', 0)}GB), triggering cleanup")
                cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=1000)
                logger.info(f"Pre-upload cleanup: {cleanup_result}")
        except Exception as storage_health_error:
            logger.error(f"Storage health check failed: {storage_health_error}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage health check failed. Please try again later."
            )

        # Prepara TUTTI i metadati archeologici da form utente (una sola volta)
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
        
        logger.info(f"📋 Processing {len(photos)} photos in parallel with metadata: {list(archaeological_metadata_from_form.keys())}")
        
        # NUOVO: Processa tutte le foto in parallelo con asyncio.gather()
        async def process_single_photo(file: UploadFile) -> Optional[dict]:
            """Processa una singola foto in modo asincrono con error handling completo"""
            photo_record = None
            filename = None
            file_path = None
            
            try:
                # 1. Salva file su MinIO con error handling
                try:
                    filename, file_path, file_size = await storage_service.save_upload_file(
                        file, str(site_id), str(current_user_id)
                    )
                except Exception as storage_error:
                    logger.error(f"Failed to save file {file.filename} to storage: {storage_error}")
                    raise HTTPException(
                        status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                        detail=f"Storage service error: Unable to save file {file.filename}"
                    )

                # 2. Estrai metadati dal file caricato con error handling
                try:
                    await file.seek(0)  # Reset file pointer
                    exif_data, metadata = await photo_metadata_service.extract_metadata_from_file(
                        file, filename
                    )
                except Exception as metadata_error:
                    logger.error(f"Failed to extract metadata from {file.filename}: {metadata_error}")
                    # Continue with empty metadata if extraction fails
                    exif_data, metadata = {}, {}

                # 3. Crea record nel database CON metadati archeologici con error handling
                try:
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
                except Exception as record_creation_error:
                    logger.error(f"Failed to create photo record for {file.filename}: {record_creation_error}")
                    # Clean up the uploaded file if record creation fails
                    try:
                        await storage_service.delete_file(file_path)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup file after record creation failure: {cleanup_error}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Database error: Unable to create photo record for {file.filename}"
                    )

                # 4. Create a NEW database session for this parallel task to avoid transaction conflicts
                from app.database.base import async_session_maker
                async with async_session_maker() as task_db:
                    try:
                        # Start transaction in the new session
                        async with task_db.begin():
                            # Add photo record to transaction
                            task_db.add(photo_record)
                            
                            # Flush to get the ID without committing
                            await task_db.flush()
                            await task_db.refresh(photo_record)
                            logger.info(f"Photo record flushed with ID: {photo_record.id}")
                            
                            # 5. Genera thumbnail DOPO che il record è stato salvato con error handling
                            try:
                                await file.seek(0)  # Reset file pointer per thumbnail
                                thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                                    file, str(photo_record.id)
                                )

                                if thumbnail_path:
                                    photo_record.thumbnail_path = thumbnail_path
                                    logger.info(f"Thumbnail generated: {thumbnail_path}")
                                else:
                                    logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")
                            except Exception as thumbnail_error:
                                logger.error(f"Thumbnail generation error for photo {photo_record.id}: {thumbnail_error}")
                                # Don't fail the entire upload if thumbnail generation fails
                                # Just log the error and continue
                            
                            # 6. Log attività con error handling
                            try:
                                activity = UserActivity(
                                    user_id=str(current_user_id),
                                    site_id=str(site_id),
                                    activity_type="UPLOAD",
                                    activity_desc=f"Caricata foto: {file.filename}",
                                    extra_data=json.dumps({
                                        "photo_id": str(photo_record.id),
                                        "filename": filename,
                                        "file_size": file_size
                                    })
                                )
                                task_db.add(activity)
                                logger.info(f"Activity log added for photo {photo_record.id}")
                            except Exception as activity_error:
                                logger.error(f"Failed to log activity for photo {photo_record.id}: {activity_error}")
                                # Don't fail the upload if activity logging fails
                        
                        # Transaction commits automatically here
                        logger.info(f"Transaction committed successfully for photo {photo_record.id}")
                        
                    except Exception as db_error:
                        logger.error(f"Database transaction failed for photo {file.filename}: {db_error}")
                        # Clean up the uploaded file if database transaction fails
                        try:
                            await storage_service.delete_file(file_path)
                        except Exception as cleanup_error:
                            logger.error(f"Failed to cleanup file after DB transaction failure: {cleanup_error}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Database error: Unable to save photo record"
                        )

                logger.info(f"Photo {photo_record.id} saved with thumbnail_path: {photo_record.thumbnail_path}")
                logger.info(f"Photo uploaded successfully: {photo_record.id} by user {current_user_id}")

                return {
                    "photo_id": str(photo_record.id),
                    "filename": filename,
                    "file_size": file_size,
                    "file_path": file_path,
                    "metadata": {
                        "width": photo_record.width,
                        "height": photo_record.height,
                        "photo_date": photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                        "camera_model": photo_record.camera_model
                    },
                    "archaeological_metadata": {
                        'inventory_number': photo_record.inventory_number,
                        'excavation_area': photo_record.excavation_area,
                        'material': photo_record.material,
                        'chronology_period': photo_record.chronology_period,
                        'photo_type': photo_record.photo_type,
                        'photographer': photo_record.photographer,
                        'description': photo_record.description,
                        'keywords': photo_record.keywords
                    }
                }
                
            except HTTPException as he:
                # Re-raise HTTP exceptions as-is
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
                logger.error(f"Unexpected error processing photo {file.filename}: {photo_error}")
                # Clean up file if it exists
                if file_path:
                    try:
                        await storage_service.delete_file(file_path)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup file after error: {cleanup_error}")
                # Return None for this photo but don't fail the entire batch
                return None

        # Processa tutte le foto in parallelo con error handling
        try:
            logger.info(f"🚀 Starting photo processing of {len(photos)} photos")
            
            # CRITICAL FIX: Sequential processing for single files to avoid session conflicts
            if len(photos) == 1:
                logger.info("📋 Processing single file sequentially to avoid database session conflicts")
                upload_results = []
                try:
                    result = await process_single_photo(photos[0])
                    upload_results.append(result)
                except Exception as e:
                    upload_results.append(e)
            else:
                # Use parallel processing for multiple files with CRITICAL timeout wrapper
                logger.info(f"🚀 Starting parallel processing of {len(photos)} photos with timeout protection")
                upload_tasks = [process_single_photo(file) for file in photos]
                
                # CRITICAL FIX: Wrap asyncio.gather() with timeout to prevent indefinite hanging
                try:
                    upload_results = await asyncio.wait_for(
                        asyncio.gather(*upload_tasks, return_exceptions=True),
                        timeout=300.0  # 5 minutes timeout
                    )
                    logger.info(f"✅ Parallel processing completed within timeout: {len(photos)} photos")
                except asyncio.TimeoutError:
                    logger.error("❌ Photo upload processing timed out after 5 minutes")
                    raise HTTPException(status_code=408, detail="Upload processing timed out after 5 minutes")
            
            # Filtra risultati validi
            uploaded_photos = []
            failed_photos = []
            
            for i, result in enumerate(upload_results):
                if isinstance(result, Exception):
                    # ENHANCED ERROR HANDLING: Provide more specific error messages for database conflicts
                    error_msg = str(result)
                    if "database" in error_msg.lower() and ("lock" in error_msg.lower() or "conflict" in error_msg.lower()):
                        error_msg = f"Database conflict during photo {photos[i].filename} processing: {error_msg}"
                    logger.error(f"❌ Upload task failed for photo {photos[i].filename}: {error_msg}")
                    failed_photos.append({
                        "filename": photos[i].filename,
                        "error": error_msg
                    })
                elif result is not None:
                    uploaded_photos.append(result)
                else:
                    # None result indicates a failed upload that was handled gracefully
                    failed_photos.append({
                        "filename": photos[i].filename,
                        "error": "Processing failed but was handled gracefully"
                    })
            
            # IMPROVED LOGGING: Detailed success/failure reporting
            success_count = len(uploaded_photos)
            failure_count = len(failed_photos)
            logger.info(f"📊 Upload processing summary: {success_count} photos uploaded successfully, {failure_count} failed out of {len(photos)} total")
            
            if failed_photos:
                logger.warning(f"⚠️ Failed uploads: {[f['filename'] + ': ' + f['error'] for f in failed_photos[:3]]}")  # Log first 3 failures
            
            # If no photos were uploaded successfully, raise an error
            if not uploaded_photos and failed_photos:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"All photo uploads failed. First error: {failed_photos[0]['error']}"
                )
                
        except Exception as parallel_error:
            logger.error(f"Parallel processing error: {parallel_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error during parallel processing: {str(parallel_error)}"
            )

        # Prepara lista foto per tiles MA NON inizia processing
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
                        photo_record.deepzoom_status = 'scheduled'
                        await db.commit()
                        
                        photos_needing_tiles.append({
                            'photo_id': photo_id,
                            'file_path': photo_data['file_path'],
                            'width': width,
                            'height': height,
                            'archaeological_metadata': photo_data.get('archaeological_metadata', {})
                        })
                else:
                    logger.info(f"Skipping tiles for small image {photo_id}: {width}x{height}")

            except Exception as e:
                logger.error(f"❌ Error checking tile requirements for photo {photo_id}: {e}")
        
        # DOPO tutti gli upload: avvia batch processing con il nuovo servizio background con error handling
        if photos_needing_tiles:
            try:
                logger.info(f"🎯 {len(photos_needing_tiles)} foto richiedono tiles - avvio batch processing con background service")
                
                # Avvia il batch processing con il nuovo servizio background
                batch_result = await deep_zoom_background_service.schedule_batch_processing(
                    photos_list=photos_needing_tiles,
                    site_id=str(site_id)
                )
                
                logger.info(f"✅ Batch tiles processing schedulato: {batch_result}")
            except Exception as batch_error:
                logger.error(f"Failed to schedule batch processing for tiles: {batch_error}")
                # Don't fail the upload if batch processing fails, just log the error
                # The tiles can be processed later manually

        # Validate uploaded_photos before returning
        if not isinstance(uploaded_photos, list):
            logger.error(f"Invalid uploaded_photos type: {type(uploaded_photos)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid response format: uploaded_photos must be a list"
            )

        # Validate each photo entry has required fields
        for i, photo in enumerate(uploaded_photos):
            if not isinstance(photo, dict):
                logger.error(f"Invalid photo entry at index {i}: {type(photo)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Invalid photo entry at index {i}: must be a dictionary"
                )
            required_fields = ['photo_id', 'filename', 'file_size']
            for field in required_fields:
                if field not in photo:
                    logger.error(f"Missing required field '{field}' in photo entry at index {i}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Invalid photo entry at index {i}: missing required field '{field}'"
                    )

        # Prepare response metadata
        response_metadata = {
            "message": f"{len(uploaded_photos)} foto caricate con successo",
            "total_uploaded": len(uploaded_photos),
            "photos_needing_tiles": len(photos_needing_tiles),
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Include failed photos information if any
        if 'failed_photos' in locals() and failed_photos:
            response_metadata["failed_photos"] = failed_photos
            response_metadata["total_failed"] = len(failed_photos)

        # Return uploaded_photos as direct field with metadata
        response_data = {
            "uploaded_photos": uploaded_photos,
            **response_metadata
        }

        logger.info(f"✅ Upload API response: {len(uploaded_photos)} foto caricate, {len(photos_needing_tiles)} necessitano tiles")

        return JSONResponse(response_data)

    except HTTPException as he:
        # Re-raise HTTP exceptions with proper status codes
        raise he
    except Exception as e:
        logger.error(f"Unexpected upload error: {str(e)}")
        # Clean up any temporary files if they exist
        try:
            if 'file_path' in locals():
                await storage_service.delete_file(file_path)
        except Exception as cleanup_error:
            logger.error(f"Failed to cleanup during error handling: {cleanup_error}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during upload: {str(e)}"
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

    # Gestione campi enum con sistema di conversione centralizzato
    try:
        from app.utils.enum_mappings import enum_converter, log_conversion_attempt
        
        # Convert photo_type
        if 'photo_type' in filtered_data and filtered_data['photo_type']:
            converted_photo_type = enum_converter.convert_to_enum(PhotoType, filtered_data['photo_type'])
            if converted_photo_type is None:
                raise HTTPException(status_code=400, detail=f"Tipo foto non valido: {filtered_data['photo_type']}")
            filtered_data['photo_type'] = converted_photo_type
            log_conversion_attempt(PhotoType, str(filtered_data['photo_type']), converted_photo_type, True)

        # Convert material
        if 'material' in filtered_data and filtered_data['material']:
            converted_material = enum_converter.convert_to_enum(MaterialType, filtered_data['material'])
            if converted_material is None:
                raise HTTPException(status_code=400, detail=f"Materiale non valido: {filtered_data['material']}")
            filtered_data['material'] = converted_material
            log_conversion_attempt(MaterialType, str(filtered_data['material']), converted_material, True)

        # Convert conservation_status
        if 'conservation_status' in filtered_data and filtered_data['conservation_status']:
            converted_conservation = enum_converter.convert_to_enum(ConservationStatus, filtered_data['conservation_status'])
            if converted_conservation is None:
                raise HTTPException(status_code=400, detail=f"Stato di conservazione non valido: {filtered_data['conservation_status']}")
            filtered_data['conservation_status'] = converted_conservation
            log_conversion_attempt(ConservationStatus, str(filtered_data['conservation_status']), converted_conservation, True)
            
    except ImportError:
        # Fallback to basic conversion if enum_mappings is not available
        logger.warning("enum_mappings not available, using basic enum conversion")
        
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
    """Elimina foto dal sito archeologico - PROTETTO contro eliminazione foto US"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    # Check if this is a US photo (which should not be deleted from here)
    us_file_query = select(USFile).where(
        and_(USFile.id == photo_id, USFile.site_id == site_id)
    )
    us_file = await db.execute(us_file_query)
    us_file = us_file.scalar_one_or_none()
    
    if us_file:
        raise HTTPException(
            status_code=403,
            detail="Questa foto appartiene a una US/USM e può essere eliminata solo dalla pagina US"
        )

    photo_query = select(Photo).where(
        and_(Photo.id == photo_id, Photo.site_id == site_id)
    )
    photo = await db.execute(photo_query)
    photo = photo.scalar_one_or_none()

    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata nel sito")

    try:
        photo_filename = photo.filename
        photo_path = photo.filepath
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
    """Elimina più foto in blocco - PROTETTO contro eliminazione foto US"""
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

        # Check for US photos in the selection
        us_files_query = select(USFile).where(
            and_(USFile.site_id == site_id, USFile.id.in_(photo_ids))
        )
        us_files = await db.execute(us_files_query)
        us_files_list = us_files.scalars().all()
        
        if us_files_list:
            us_count = len(us_files_list)
            raise HTTPException(
                status_code=403,
                detail=f"{us_count} foto appartengono a US/USM e non possono essere eliminate da qui"
            )

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
                photo_path = photo.filepath
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
                    user_id=str(current_user_id),
                    site_id=str(site_id),
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

        # Delete all photos first without nested transaction
        for photo in photos:
            try:
                photo_filename = photo.filename
                photo_path = photo.filepath
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
                    user_id=str(current_user_id),
                    site_id=str(site_id),
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

        # Commit all changes at once
        try:
            await db.commit()
            logger.info(f"Bulk delete transaction committed successfully for {deleted_count} photos")
        except Exception as e:
            logger.error(f"Bulk delete transaction error: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Errore eliminazione in blocco: {str(e)}")

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

        # Gestione campi enum con sistema di conversione centralizzato
        try:
            from app.utils.enum_mappings import enum_converter, log_conversion_attempt
            
            # Convert photo_type
            if 'photo_type' in filtered_metadata and filtered_metadata['photo_type']:
                converted_photo_type = enum_converter.convert_to_enum(PhotoType, filtered_metadata['photo_type'])
                if converted_photo_type is None:
                    raise HTTPException(status_code=400, detail=f"Tipo foto non valido: {filtered_metadata['photo_type']}")
                filtered_metadata['photo_type'] = converted_photo_type
                log_conversion_attempt(PhotoType, str(filtered_metadata['photo_type']), converted_photo_type, True)

            # Convert material
            if 'material' in filtered_metadata and filtered_metadata['material']:
                converted_material = enum_converter.convert_to_enum(MaterialType, filtered_metadata['material'])
                if converted_material is None:
                    raise HTTPException(status_code=400, detail=f"Materiale non valido: {filtered_metadata['material']}")
                filtered_metadata['material'] = converted_material
                log_conversion_attempt(MaterialType, str(filtered_metadata['material']), converted_material, True)

            # Convert conservation_status
            if 'conservation_status' in filtered_metadata and filtered_metadata['conservation_status']:
                converted_conservation = enum_converter.convert_to_enum(ConservationStatus, filtered_metadata['conservation_status'])
                if converted_conservation is None:
                    raise HTTPException(status_code=400, detail=f"Stato di conservazione non valido: {filtered_metadata['conservation_status']}")
                filtered_metadata['conservation_status'] = converted_conservation
                log_conversion_attempt(ConservationStatus, str(filtered_metadata['conservation_status']), converted_conservation, True)
                
        except ImportError:
            # Fallback to basic conversion if enum_mappings is not available
            logger.warning("enum_mappings not available, using basic enum conversion")
            
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

        # Use a transaction for all database operations
        try:
            async with db.begin():
                # Update all photos first
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

                # Log activity after all updates
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
            
            # Transaction commits automatically here
            logger.info(f"Bulk update transaction committed successfully for {updated_count} photos")
            
        except Exception as e:
            logger.error(f"Bulk update transaction error: {e}")
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Errore aggiornamento in blocco: {str(e)}")

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


@photos_router.post("/site/{site_id}/photos/deep-zoom/start-background")
async def start_deep_zoom_background_processor(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id)
):
    """Avvia il processore background per deep zoom tiles"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        await deep_zoom_background_service.start_background_processor()
        
        logger.info(f"Deep zoom background processor started by user {current_user_id} for site {site_id}")
        
        return {
            "message": "Deep zoom background processor started successfully",
            "site_id": str(site_id),
            "started_by": str(current_user_id),
            "started_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start deep zoom background processor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start background processor: {str(e)}"
        )


@photos_router.post("/site/{site_id}/photos/deep-zoom/stop-background")
async def stop_deep_zoom_background_processor(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access),
        current_user_id: UUID = Depends(get_current_user_id)
):
    """Ferma il processore background per deep zoom tiles"""
    site, permission = site_access

    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")

    try:
        await deep_zoom_background_service.stop_background_processor()
        
        logger.info(f"Deep zoom background processor stopped by user {current_user_id} for site {site_id}")
        
        return {
            "message": "Deep zoom background processor stopped successfully",
            "site_id": str(site_id),
            "stopped_by": str(current_user_id),
            "stopped_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop deep zoom background processor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop background processor: {str(e)}"
        )


@photos_router.get("/site/{site_id}/photos/deep-zoom/background-status")
async def get_deep_zoom_background_status(
        site_id: UUID,
        site_access: tuple = Depends(get_site_access)
):
    """Ottieni lo stato del processore background per deep zoom tiles"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        queue_status = await deep_zoom_background_service.get_queue_status()
        
        return {
            "site_id": str(site_id),
            "background_status": queue_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get deep zoom background status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get background status: {str(e)}"
        )


@photos_router.get("/site/{site_id}/photos/{photo_id}/deep-zoom/task-status")
async def get_photo_deep_zoom_task_status(
        site_id: UUID,
        photo_id: UUID,
        site_access: tuple = Depends(get_site_access)
):
    """Ottieni lo stato del task di processing per una foto specifica"""
    site, permission = site_access

    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")

    try:
        task_status = await deep_zoom_background_service.get_task_status(str(photo_id))
        
        if not task_status:
            # Fallback to processing status from MinIO
            processing_status = await deep_zoom_minio_service.get_processing_status(str(site_id), str(photo_id))
            
            return {
                "site_id": str(site_id),
                "photo_id": str(photo_id),
                "task_status": None,
                "processing_status": processing_status,
                "message": "Task not found in background service, checking MinIO status"
            }
        
        return {
            "site_id": str(site_id),
            "photo_id": str(photo_id),
            "task_status": task_status,
            "message": "Task status from background service"
        }
        
    except Exception as e:
        logger.error(f"Failed to get photo deep zoom task status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task status: {str(e)}"
        )


async def _handle_queued_upload(
        site_id: UUID,
        photos: List[UploadFile],
        title: Optional[str],
        description: Optional[str],
        photo_type: Optional[str],
        photographer: Optional[str],
        keywords: Optional[str],
        inventory_number: Optional[str],
        catalog_number: Optional[str],
        excavation_area: Optional[str],
        stratigraphic_unit: Optional[str],
        grid_square: Optional[str],
        depth_level: Optional[float],
        find_date: Optional[str],
        finder: Optional[str],
        excavation_campaign: Optional[str],
        material: Optional[str],
        material_details: Optional[str],
        object_type: Optional[str],
        object_function: Optional[str],
        length_cm: Optional[float],
        width_cm: Optional[float],
        height_cm: Optional[float],
        diameter_cm: Optional[float],
        weight_grams: Optional[float],
        chronology_period: Optional[str],
        chronology_culture: Optional[str],
        dating_from: Optional[str],
        dating_to: Optional[str],
        dating_notes: Optional[str],
        conservation_status: Optional[str],
        conservation_notes: Optional[str],
        restoration_history: Optional[str],
        bibliography: Optional[str],
        comparative_references: Optional[str],
        external_links: Optional[str],
        copyright_holder: Optional[str],
        license_type: Optional[str],
        usage_rights: Optional[str],
        site_access: tuple,
        current_user_id: UUID,
        db: AsyncSession,
        priority: str = "normal"
):
    """Handle upload through queue system"""
    
    from app.services.request_queue_service import request_queue_service, RequestPriority
    
    # Map priority string to enum
    priority_map = {
        "critical": RequestPriority.CRITICAL,
        "high": RequestPriority.HIGH,
        "normal": RequestPriority.NORMAL,
        "low": RequestPriority.LOW,
        "bulk": RequestPriority.BULK
    }
    
    request_priority = priority_map.get(priority.lower(), RequestPriority.NORMAL)
    
    # Prepare upload data for queue
    upload_data = {
        'site_id': str(site_id),
        'user_id': str(current_user_id),
        'photos_count': len(photos),
        'metadata': {
            'title': title,
            'description': description,
            'photo_type': photo_type,
            'photographer': photographer,
            'keywords': keywords,
            'inventory_number': inventory_number,
            'catalog_number': catalog_number,
            'excavation_area': excavation_area,
            'stratigraphic_unit': stratigraphic_unit,
            'grid_square': grid_square,
            'depth_level': depth_level,
            'find_date': find_date,
            'finder': finder,
            'excavation_campaign': excavation_campaign,
            'material': material,
            'material_details': material_details,
            'object_type': object_type,
            'object_function': object_function,
            'length_cm': length_cm,
            'width_cm': width_cm,
            'height_cm': height_cm,
            'diameter_cm': diameter_cm,
            'weight_grams': weight_grams,
            'chronology_period': chronology_period,
            'chronology_culture': chronology_culture,
            'dating_from': dating_from,
            'dating_to': dating_to,
            'dating_notes': dating_notes,
            'conservation_status': conservation_status,
            'conservation_notes': conservation_notes,
            'restoration_history': restoration_history,
            'bibliography': bibliography,
            'comparative_references': comparative_references,
            'external_links': external_links,
            'copyright_holder': copyright_holder,
            'license_type': license_type,
            'usage_rights': usage_rights
        }
    }
    
    # Estimate processing time based on file count
    estimated_duration = len(photos) * 30  # 30 seconds per photo estimate
    
    try:
        # Enqueue upload request
        request_id = await request_queue_service.enqueue_request(
            request_type="POST_/api/site/{site_id}/photos/upload",
            payload=upload_data,
            priority=request_priority,
            user_id=str(current_user_id),
            site_id=str(site_id),
            timeout_seconds=600 + (len(photos) * 60),  # Base 10min + 1min per photo
            max_retries=3,
            estimated_duration=estimated_duration
        )
        
        # Store files temporarily for queue processing
        temp_files = []
        upload_paths = []
        
        try:
            from app.services.storage_service import storage_service
            
            for photo in photos:
                # Save to temporary location
                filename, file_path, file_size = await storage_service.save_upload_file(
                    photo, str(site_id), str(current_user_id), temp=True
                )
                temp_files.append({
                    'filename': filename,
                    'file_path': file_path,
                    'file_size': file_size,
                    'original_filename': photo.filename
                })
                upload_paths.append(file_path)
            
            # Update request payload with file info
            upload_data['temp_files'] = temp_files
            
            logger.info(f"Queued upload request {request_id} for {len(photos)} photos with priority {request_priority.name}")
            
            return JSONResponse({
                'message': f'Upload queued for processing',
                'request_id': request_id,
                'status': 'queued',
                'priority': request_priority.name,
                'photos_count': len(photos),
                'estimated_wait': await request_queue_service._estimate_wait_time(request_priority),
                'queue_status_url': f'/api/queue/request/{request_id}'
            }, status_code=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            # Clean up temp files if queueing fails
            logger.error(f"Failed to prepare temp files for queue: {e}")
            try:
                from app.services.storage_service import storage_service
                for file_path in upload_paths:
                    await storage_service.delete_file(file_path)
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup temp files: {cleanup_error}")
            raise
            
    except Exception as e:
        logger.error(f"Failed to queue upload request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue upload: {str(e)}"
        )


async def process_queued_upload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process queued upload request"""

    from app.services.storage_service import storage_service
    from app.services.photo_metadata_service import photo_metadata_service
    from app.services.deep_zoom_background_service import deep_zoom_background_service
    from app.models import Photo
    from sqlalchemy import select
    import uuid
    import aiofiles
    from io import BytesIO

    logger.info(f"Processing queued upload for site {payload['site_id']}")

    try:
        site_id = uuid.UUID(payload['site_id'])
        user_id = uuid.UUID(payload['user_id'])
        metadata = payload['metadata']
        temp_files = payload.get('temp_files', [])

        # Process each photo
        uploaded_photos = []
        photos_needing_tiles = []

        for temp_file in temp_files:
            try:
                # Check if temp file exists before moving
                from app.services.storage_service import storage_service
                temp_file_exists = await storage_service.file_exists(temp_file['file_path'])
                if not temp_file_exists:
                    logger.error(f"Temp file not found: {temp_file['file_path']}")
                    continue

                # Move temp file to permanent location
                permanent_path = await storage_service.move_temp_file(
                    temp_file['file_path'],
                    str(site_id),
                    str(user_id)
                )

                # Extract metadata from the actual file
                file_metadata = {}
                try:
                    # Create a file-like object from the permanent path for metadata extraction
                    async with aiofiles.open(permanent_path, 'rb') as f:
                        # Create a simple file-like object for metadata extraction
                        content = await f.read()
                        file_like = BytesIO(content)
                        file_like.filename = temp_file['original_filename']

                        exif_data, extracted_metadata = await photo_metadata_service.extract_metadata_from_file(
                            file_like, temp_file['filename']
                        )
                        file_metadata = extracted_metadata
                except Exception as metadata_error:
                    logger.warning(f"Failed to extract metadata for {temp_file.get('filename')}: {metadata_error}")
                    # Continue with empty metadata if extraction fails

                # Create photo record
                photo_record = await photo_metadata_service.create_photo_record(
                    filename=temp_file['filename'],
                    original_filename=temp_file['original_filename'],
                    file_path=permanent_path,
                    file_size=temp_file['file_size'],
                    site_id=str(site_id),
                    uploaded_by=str(user_id),
                    metadata=file_metadata,
                    archaeological_metadata=metadata
                )

                # Save to database
                from app.database.base import async_session_maker
                async with async_session_maker() as db:
                    try:
                        db.add(photo_record)
                        await db.commit()
                        await db.refresh(photo_record)
                        logger.info(f"Photo record saved with ID: {photo_record.id}")
                    except Exception as db_commit_error:
                        logger.error(f"Database commit failed for queued photo {temp_file.get('filename')}: {db_commit_error}")
                        # Don't try to rollback here - let the session handle it naturally
                        raise Exception(f"Database error: Unable to save photo record: {db_commit_error}")

                    # Generate thumbnail after database save
                    try:
                        async with aiofiles.open(permanent_path, 'rb') as f:
                            content = await f.read()
                            file_like = BytesIO(content)
                            file_like.filename = temp_file['original_filename']

                            thumbnail_path = await photo_metadata_service.generate_thumbnail_from_file(
                                file_like, str(photo_record.id)
                            )

                            if thumbnail_path:
                                photo_record.thumbnail_path = thumbnail_path
                                try:
                                    await db.commit()
                                    logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
                                except Exception as thumbnail_commit_error:
                                    logger.error(f"Failed to commit thumbnail update: {thumbnail_commit_error}")
                                    # Don't try to rollback here - let the session handle it naturally
                            else:
                                logger.warning(f"Thumbnail generation failed for photo {photo_record.id}")
                    except Exception as thumbnail_error:
                        logger.error(f"Thumbnail generation error for photo {photo_record.id}: {thumbnail_error}")
                        # Don't fail the upload if thumbnail generation fails

                uploaded_photos.append({
                    'photo_id': str(photo_record.id),
                    'filename': temp_file['filename'],
                    'original_filename': temp_file['original_filename'],
                    'file_size': temp_file['file_size'],
                    'file_path': permanent_path,
                    'metadata': {
                        'width': photo_record.width,
                        'height': photo_record.height,
                        'photo_date': photo_record.photo_date.isoformat() if photo_record.photo_date else None,
                        'camera_model': photo_record.camera_model
                    },
                    'archaeological_metadata': {
                        'inventory_number': photo_record.inventory_number,
                        'excavation_area': photo_record.excavation_area,
                        'material': photo_record.material,
                        'chronology_period': photo_record.chronology_period,
                        'photo_type': photo_record.photo_type,
                        'photographer': photo_record.photographer,
                        'description': photo_record.description,
                        'keywords': photo_record.keywords
                    }
                })

                # Check if tiles are needed (larger files or high resolution)
                width = photo_record.width or 0
                height = photo_record.height or 0
                max_dimension = max(width, height)
                file_size_mb = temp_file['file_size'] / (1024 * 1024)

                if max_dimension > 2000 or file_size_mb > 5:  # Large images need tiles
                    photos_needing_tiles.append({
                        'photo_id': str(photo_record.id),
                        'file_path': permanent_path,
                        'width': width,
                        'height': height,
                        'archaeological_metadata': metadata
                    })

                logger.info(f"Queued upload: Successfully processed photo {photo_record.id} ({temp_file['original_filename']})")

            except Exception as e:
                logger.error(f"Error processing queued photo {temp_file.get('filename')}: {e}")
                continue

        # Schedule tile processing if needed
        if photos_needing_tiles:
            try:
                await deep_zoom_background_service.schedule_batch_processing(
                    photos_list=photos_needing_tiles,
                    site_id=str(site_id)
                )
                logger.info(f"Scheduled deep zoom processing for {len(photos_needing_tiles)} photos")
            except Exception as tile_error:
                logger.error(f"Failed to schedule tile processing: {tile_error}")
                # Don't fail entire upload if tile scheduling fails

        return {
            'status': 'completed',
            'message': f'Processed {len(uploaded_photos)} photos successfully',
            'uploaded_photos': uploaded_photos,
            'photos_needing_tiles': len(photos_needing_tiles),
            'processed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error processing queued upload: {e}")
        raise Exception(f"Upload processing failed: {str(e)}")
        

