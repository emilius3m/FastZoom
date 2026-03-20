# app/services/photos/query_service.py - Photo query business logic service

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from uuid import UUID
from collections import defaultdict
import re
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from loguru import logger

from app.models import Photo, PhotoType, MaterialType, ConservationStatus
from app.models import USFile
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria, us_files_association, usm_files_association
from app.models.tma import SchedaTMA, TMAFotografia
from app.schemas.photos import PhotoQueryFilters
from app.routes.api.dependencies import normalize_site_id


class PhotoQueryService:
    """
    Service class for handling photo query logic and building complex filters.
    Separates query concerns from routing layer for better testability and maintainability.
    """

    def __init__(self):
        self.supported_sort_options = {
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

    async def query_site_photos(
        self,
        site_id: str,
        filters: PhotoQueryFilters,
        db: AsyncSession
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Query photos for a site with comprehensive archaeological filtering.
        
        Returns:
            Tuple of (general_photos_data, us_photos_data)
        """
        logger.info(f"Querying photos for site {site_id} with filters: {filters.dict(exclude_unset=True)}")
        
        # Normalize site ID
        normalized_site_id = normalize_site_id(site_id)
        if not normalized_site_id:
            logger.error(f"Invalid site ID: {site_id}")
            return [], []
        
        # Query general photos from Photo table
        general_photos = await self._query_general_photos(normalized_site_id, filters, db)
        
        # Query US photos from USFile table
        us_photos = await self._query_us_photos(normalized_site_id, filters, db)
        
        # Combine and format results
        photos_data = []
        photos_data.extend(general_photos)
        photos_data.extend(us_photos)
        
        logger.info(
            f"Photo query completed: {len(general_photos)} general photos + {len(us_photos)} US photos = {len(photos_data)} total"
        )
        
        return general_photos, us_photos

    async def _query_general_photos(
        self,
        normalized_site_id: str,
        filters: PhotoQueryFilters,
        db: AsyncSession
    ) -> List[Dict]:
        """Query general photos from Photo table with applied filters."""
        
        # Build base query
        photos_query = select(Photo).where(Photo.site_id == normalized_site_id)
        
        # Apply filters
        photos_query = self._apply_basic_filters(photos_query, filters)
        photos_query = self._apply_archaeological_filters(photos_query, filters)
        photos_query = self._apply_status_filters(photos_query, filters)
        photos_query = self._apply_date_filters(photos_query, filters)
        photos_query = self._apply_dimension_filters(photos_query, filters)
        photos_query = self._apply_metadata_presence_filters(photos_query, filters)
        photos_query = self._apply_sorting(photos_query, filters)
        
        # Execute query
        photos = await db.execute(photos_query)
        photos = photos.scalars().all()

        # Build TMA references map (photo_id -> list of references)
        tma_references_map = await self._build_tma_references_for_photos(
            normalized_site_id=normalized_site_id,
            photos=photos,
            db=db,
        )
        
        # Convert to dictionary format with URLs
        photos_data = []
        for photo in photos:
            photo_dict = photo.to_dict()
            photo_dict['file_url'] = f"/api/v1/photos/{photo.id}/full"
            photo_dict['thumbnail_url'] = f"/api/v1/photos/{photo.id}/thumbnail"
            photo_dict['download_url'] = f"/api/v1/photos/{photo.id}/download"
            photo_dict['upload_date'] = photo.created_at.isoformat() if photo.created_at else None
            photo_dict['tags'] = photo.get_keywords_list()
            photo_dict['source_type'] = 'photo'  # Mark as general photo
            photo_dict['tma_references'] = tma_references_map.get(str(photo.id), [])
            photo_dict['has_tma_references'] = len(photo_dict['tma_references']) > 0
            photos_data.append(photo_dict)
        
        return photos_data

    @staticmethod
    def _extract_photo_api_id(path: str) -> Optional[str]:
        """Extract photo_id from /api/v1/photos/{id}/{variant} path (also absolute URLs)."""
        raw = (path or "").strip()
        if not raw:
            return None

        parsed_path = urlparse(raw).path if (raw.startswith("http://") or raw.startswith("https://")) else raw
        match = re.match(r"^/api/v1/photos/([0-9a-fA-F-]{36})/(thumbnail|view|full|download)$", parsed_path)
        if not match:
            return None
        return match.group(1)

    @staticmethod
    def _collect_photo_match_candidates(photo: Photo) -> set[str]:
        """Collect all candidate identifiers/paths that can match a TMA foto file_path."""
        candidates: set[str] = set()
        photo_id = str(photo.id)

        # API-style references
        for variant in ("thumbnail", "view", "full", "download"):
            candidates.add(f"/api/v1/photos/{photo_id}/{variant}")

        # Storage-backed paths
        filepath = (photo.filepath or "").strip()
        if filepath:
            candidates.add(filepath)

        thumbnail_path = (photo.thumbnail_path or "").strip()
        if thumbnail_path:
            candidates.add(thumbnail_path)

        return candidates

    async def _build_tma_references_for_photos(
        self,
        normalized_site_id: str,
        photos: List[Photo],
        db: AsyncSession,
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Build mapping photo_id -> TMA references, matching on:
        - API-style path (/api/v1/photos/{id}/{variant})
        - absolute URL containing the same API path
        - stored Photo.filepath / Photo.thumbnail_path
        """
        if not photos:
            return {}

        photo_ids = {str(photo.id) for photo in photos}
        references_map: Dict[str, List[Dict[str, str]]] = {photo_id: [] for photo_id in photo_ids}

        candidate_to_photo_ids: Dict[str, set[str]] = defaultdict(set)
        for photo in photos:
            photo_id = str(photo.id)
            for candidate in self._collect_photo_match_candidates(photo):
                candidate_to_photo_ids[candidate].add(photo_id)

        tma_query = (
            select(
                SchedaTMA.id.label("record_id"),
                SchedaTMA.nctr.label("nctr"),
                SchedaTMA.nctn.label("nctn"),
                TMAFotografia.file_path.label("file_path"),
            )
            .join(TMAFotografia, TMAFotografia.scheda_id == SchedaTMA.id)
            .where(SchedaTMA.site_id == normalized_site_id)
        )

        rows = (await db.execute(tma_query)).all()
        seen_per_photo: Dict[str, set[str]] = defaultdict(set)

        for row in rows:
            raw_path = (row.file_path or "").strip()
            if not raw_path:
                continue

            matched_photo_ids: set[str] = set()

            # 1) Direct API photo path matching
            api_photo_id = self._extract_photo_api_id(raw_path)
            if api_photo_id and api_photo_id in photo_ids:
                matched_photo_ids.add(api_photo_id)

            # 2) Direct path/object matching
            if raw_path in candidate_to_photo_ids:
                matched_photo_ids.update(candidate_to_photo_ids[raw_path])

            # 3) Absolute URL fallback (path part)
            if raw_path.startswith("http://") or raw_path.startswith("https://"):
                parsed_path = urlparse(raw_path).path
                if parsed_path in candidate_to_photo_ids:
                    matched_photo_ids.update(candidate_to_photo_ids[parsed_path])

            if not matched_photo_ids:
                continue

            nctr = (row.nctr or "").strip()
            nctn = str(row.nctn or "").strip().zfill(8)
            nct = f"{nctr}{nctn}" if (nctr or nctn) else ""

            ref = {
                "record_id": str(row.record_id),
                "nct": nct,
                "label": nct if nct else "Scheda",
            }

            for matched_photo_id in matched_photo_ids:
                if ref["record_id"] in seen_per_photo[matched_photo_id]:
                    continue
                references_map.setdefault(matched_photo_id, []).append(ref)
                seen_per_photo[matched_photo_id].add(ref["record_id"])

        return references_map

    async def _query_us_photos(
        self,
        normalized_site_id: str,
        filters: PhotoQueryFilters,
        db: AsyncSession
    ) -> List[Dict]:
        """Query US photos from USFile table with applied filters."""

        # USFile entries do not expose tag metadata; when tag filter is active,
        # keep results coherent by excluding US photos.
        if filters.tags and filters.tags.strip():
            return []
        
        # Build base query for US files with eager loading
        us_files_query = select(USFile).where(
            and_(
                USFile.site_id == normalized_site_id,
                USFile.file_category == 'fotografia'
            )
        ).options(
            # Eager load US and USM associations to avoid N+1 queries
            selectinload(USFile.us_associations),
            selectinload(USFile.usm_associations)
        )
        
        # Apply search filter to USFile query (basic search only)
        if filters.search:
            search_term = f"%{filters.search}%"
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
        
        # Get US/USM associations for these files (now uses pre-loaded data)
        us_associations_map = self._get_us_associations(us_files)
        
        # Convert to unified dictionary format
        us_photos_data = []
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
                "tags": [],  # US files don't have tags
                "tma_references": [],
                "has_tma_references": False,
            }
            us_photos_data.append(us_photo_dict)
        
        return us_photos_data

    def _get_us_associations(
        self,
        us_files: List[USFile]
    ) -> Dict[str, List[str]]:
        """
        Get US/USM associations for the given US files using pre-loaded data.
        
        This method now uses the eagerly loaded relationships from USFile objects
        instead of making separate database queries, which eliminates the N+1 problem.
        """
        us_associations_map = {}  # {file_id: [list of US codes]}

        try:
            for us_file in us_files:
                file_id = str(us_file.id)
                associations = []
                
                # Get US associations from pre-loaded data
                if hasattr(us_file, 'us_associations') and us_file.us_associations:
                    for us in us_file.us_associations:
                        if us.us_code:
                            associations.append(f"US {us.us_code}")
                
                # Get USM associations from pre-loaded data
                if hasattr(us_file, 'usm_associations') and us_file.usm_associations:
                    for usm in us_file.usm_associations:
                        if usm.usm_code:
                            associations.append(f"USM {usm.usm_code}")
                
                # Only add to map if there are associations
                if associations:
                    us_associations_map[file_id] = associations

        except Exception as e:
            logger.error(f"Error getting US associations from pre-loaded data: {e}")
            # Don't fail the entire query if associations fail

        return us_associations_map

    def _apply_basic_filters(self, query, filters: PhotoQueryFilters):
        """Apply basic search and photo type filters."""
        
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Photo.filename.ilike(search_term),
                    Photo.title.ilike(search_term),
                    Photo.description.ilike(search_term),
                    Photo.inventory_number.ilike(search_term),
                    Photo.keywords.ilike(search_term)
                )
            )

        if filters.tags:
            # Support comma-separated tags; all provided tags must be present
            requested_tags = [t.strip().lower() for t in filters.tags.split(',') if t and t.strip()]
            if requested_tags:
                normalized_keywords = func.lower(func.replace(func.coalesce(Photo.keywords, ''), ' ', ''))
                for tag in requested_tags:
                    normalized_tag = tag.replace(' ', '')
                    query = query.where(
                        or_(
                            normalized_keywords == normalized_tag,
                            normalized_keywords.like(f"{normalized_tag},%"),
                            normalized_keywords.like(f"%,{normalized_tag},%"),
                            normalized_keywords.like(f"%,{normalized_tag}")
                        )
                    )

        if filters.photo_type:
            try:
                # Try to convert Italian photo type to enum
                from app.utils.enum_mappings import enum_converter
                converted_photo_type = enum_converter.convert_to_enum(PhotoType, filters.photo_type)
                if converted_photo_type:
                    query = query.where(Photo.photo_type == converted_photo_type)
                else:
                    logger.warning(f"Invalid photo_type filter: {filters.photo_type}")
            except (ValueError, ImportError):
                try:
                    # Fallback to direct enum conversion
                    query = query.where(Photo.photo_type == PhotoType(filters.photo_type))
                except ValueError:
                    logger.warning(f"Invalid photo_type filter: {filters.photo_type}")
        
        return query

    def _apply_archaeological_filters(self, query, filters: PhotoQueryFilters):
        """Apply archaeological context filters."""
        
        if filters.material:
            try:
                # Try to convert Italian material to enum
                from app.utils.enum_mappings import enum_converter
                converted_material = enum_converter.convert_to_enum(MaterialType, filters.material)
                if converted_material:
                    query = query.where(Photo.material == converted_material)
                else:
                    logger.warning(f"Invalid material filter: {filters.material}")
            except (ValueError, ImportError):
                try:
                    # Fallback to direct enum conversion
                    query = query.where(Photo.material == MaterialType(filters.material))
                except ValueError:
                    logger.warning(f"Invalid material filter: {filters.material}")

        if filters.conservation_status:
            try:
                # Try to convert Italian conservation status to enum
                from app.utils.enum_mappings import enum_converter
                converted_conservation = enum_converter.convert_to_enum(ConservationStatus, filters.conservation_status)
                if converted_conservation:
                    query = query.where(Photo.conservation_status == converted_conservation)
                else:
                    logger.warning(f"Invalid conservation_status filter: {filters.conservation_status}")
            except (ValueError, ImportError):
                try:
                    # Fallback to direct enum conversion
                    query = query.where(Photo.conservation_status == ConservationStatus(filters.conservation_status))
                except ValueError:
                    logger.warning(f"Invalid conservation_status filter: {filters.conservation_status}")

        if filters.excavation_area:
            query = query.where(Photo.excavation_area.ilike(f"%{filters.excavation_area}%"))

        if filters.stratigraphic_unit:
            query = query.where(Photo.stratigraphic_unit.ilike(f"%{filters.stratigraphic_unit}%"))

        if filters.chronology_period:
            query = query.where(Photo.chronology_period.ilike(f"%{filters.chronology_period}%"))

        if filters.object_type:
            query = query.where(Photo.object_type.ilike(f"%{filters.object_type}%"))
        
        return query

    def _apply_status_filters(self, query, filters: PhotoQueryFilters):
        """Apply status filters."""
        
        if filters.is_published is not None:
            query = query.where(Photo.is_published == filters.is_published)

        if filters.is_validated is not None:
            query = query.where(Photo.is_validated == filters.is_validated)

        if filters.has_deep_zoom is not None:
            query = query.where(Photo.has_deep_zoom == filters.has_deep_zoom)
        
        return query

    def _apply_date_filters(self, query, filters: PhotoQueryFilters):
        """Apply date range filters."""
        
        # Upload date filters
        if filters.upload_date_from:
            try:
                date_from = datetime.fromisoformat(filters.upload_date_from)
                query = query.where(Photo.created_at >= date_from)
            except ValueError:
                logger.warning(f"Invalid upload_date_from filter: {filters.upload_date_from}")

        if filters.upload_date_to:
            try:
                date_to = datetime.fromisoformat(filters.upload_date_to)
                query = query.where(Photo.created_at <= date_to)
            except ValueError:
                logger.warning(f"Invalid upload_date_to filter: {filters.upload_date_to}")

        # Photo date filters
        if filters.photo_date_from:
            try:
                date_from = datetime.fromisoformat(filters.photo_date_from)
                query = query.where(Photo.photo_date >= date_from)
            except ValueError:
                logger.warning(f"Invalid photo_date_from filter: {filters.photo_date_from}")

        if filters.photo_date_to:
            try:
                date_to = datetime.fromisoformat(filters.photo_date_to)
                query = query.where(Photo.photo_date <= date_to)
            except ValueError:
                logger.warning(f"Invalid photo_date_to filter: {filters.photo_date_to}")

        # Find date filters
        if filters.find_date_from:
            try:
                date_from = datetime.fromisoformat(filters.find_date_from)
                query = query.where(Photo.find_date >= date_from)
            except ValueError:
                logger.warning(f"Invalid find_date_from filter: {filters.find_date_from}")

        if filters.find_date_to:
            try:
                date_to = datetime.fromisoformat(filters.find_date_to)
                query = query.where(Photo.find_date <= date_to)
            except ValueError:
                logger.warning(f"Invalid find_date_to filter: {filters.find_date_to}")
        
        return query

    def _apply_dimension_filters(self, query, filters: PhotoQueryFilters):
        """Apply dimension and file size filters."""
        
        if filters.min_width:
            query = query.where(Photo.width >= filters.min_width)

        if filters.max_width:
            query = query.where(Photo.width <= filters.max_width)

        if filters.min_height:
            query = query.where(Photo.height >= filters.min_height)

        if filters.max_height:
            query = query.where(Photo.height <= filters.max_height)

        if filters.min_file_size_mb:
            query = query.where(Photo.file_size >= int(filters.min_file_size_mb * 1024 * 1024))

        if filters.max_file_size_mb:
            query = query.where(Photo.file_size <= int(filters.max_file_size_mb * 1024 * 1024))
        
        return query

    def _apply_metadata_presence_filters(self, query, filters: PhotoQueryFilters):
        """Apply metadata presence filters."""
        
        if filters.has_inventory:
            if filters.has_inventory:
                query = query.where(Photo.inventory_number.isnot(None))
            else:
                query = query.where(Photo.inventory_number.is_(None))

        if filters.has_description:
            if filters.has_description:
                query = query.where(Photo.description.isnot(None))
            else:
                query = query.where(Photo.description.is_(None))

        if filters.has_photographer:
            if filters.has_photographer:
                query = query.where(Photo.photographer.isnot(None))
            else:
                query = query.where(Photo.photographer.is_(None))
        
        return query

    def _apply_sorting(self, query, filters: PhotoQueryFilters):
        """Apply sorting to the query."""
        
        sort_by = filters.sort_by or "created_desc"
        
        if sort_by in self.supported_sort_options:
            query = query.order_by(self.supported_sort_options[sort_by])
        else:
            logger.warning(f"Unsupported sort option: {sort_by}, using default")
            query = query.order_by(Photo.created_at.desc())
        
        return query


# Global service instance - stateless service for dependency injection
photo_query_service = PhotoQueryService()
