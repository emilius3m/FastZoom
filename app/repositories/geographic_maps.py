"""Repository for geographic map operations."""

from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, delete
from sqlalchemy.orm import selectinload
from app.models.geographic_maps import (
    GeographicMap, 
    GeographicMapLayer, 
    GeographicMapMarker, 
    GeographicMapMarkerPhoto
)

from app.repositories.base import BaseRepository
from app.models.documentation_and_field import Photo

class GeographicMapRepository:
    """Repository for geographic map operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def get_site_maps(self, site_id: UUID) -> List[GeographicMap]:
        """Get all geographic maps for a site."""
        query = select(GeographicMap).where(
            and_(
                GeographicMap.site_id == str(site_id),
                GeographicMap.is_active == True
            )
        ).order_by(GeographicMap.is_default.desc(), GeographicMap.created_at.desc())
        
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_map_by_id(self, map_id: UUID, site_id: UUID) -> Optional[GeographicMap]:
        """Get a specific map by ID and site ID."""
        query = select(GeographicMap).where(
            and_(
                GeographicMap.id == str(map_id),
                GeographicMap.site_id == str(site_id)
            )
        )
        
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def get_map_with_layers_and_markers(self, map_id: UUID, site_id: UUID) -> Optional[GeographicMap]:
        """Get a map with its layers and markers loaded."""
        from app.models.documentation_and_field import Photo
        
        query = select(GeographicMap).options(
            selectinload(GeographicMap.geojson_layers),
            selectinload(GeographicMap.manual_markers).selectinload(
                GeographicMapMarker.photo_associations
            ).selectinload(GeographicMapMarkerPhoto.photo)
        ).where(
            and_(
                GeographicMap.id == str(map_id),
                GeographicMap.site_id == str(site_id)
            )
        )
        
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def create_map(self, map_data: Dict[str, Any]) -> GeographicMap:
        """Create a new geographic map."""
        new_map = GeographicMap(**map_data)
        self.db_session.add(new_map)
        await self.db_session.flush()
        return new_map

    async def update_map_default_status(self, site_id: UUID, exclude_map_id: UUID = None):
        """Update is_default status for maps in a site, setting others to False."""
        stmt = GeographicMap.__table__.update().where(
            and_(
                GeographicMap.site_id == str(site_id),
                GeographicMap.is_default == True
            )
        ).values(is_default=False)
        
        if exclude_map_id:
            stmt = stmt.where(GeographicMap.id != str(exclude_map_id))
        
        await self.db_session.execute(stmt)

    async def delete_map(self, map_id: UUID) -> bool:
        """Delete a geographic map (CASCADE will handle layers and markers)."""
        stmt = delete(GeographicMap).where(GeographicMap.id == str(map_id))
        result = await self.db_session.execute(stmt)
        return result.rowcount > 0

    async def get_map_layers(self, map_id: UUID) -> List[GeographicMapLayer]:
        """Get all layers for a specific map."""
        query = select(GeographicMapLayer).where(GeographicMapLayer.map_id == str(map_id))
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def create_layer(self, layer_data: Dict[str, Any]) -> GeographicMapLayer:
        """Create a new geographic map layer."""
        layer = GeographicMapLayer(**layer_data)
        self.db_session.add(layer)
        await self.db_session.flush()
        return layer

    async def get_map_markers(self, map_id: UUID) -> List[GeographicMapMarker]:
        """Get all markers for a specific map."""
        query = select(GeographicMapMarker).where(GeographicMapMarker.map_id == str(map_id))
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def create_marker(self, marker_data: Dict[str, Any]) -> GeographicMapMarker:
        """Create a new geographic map marker."""
        marker = GeographicMapMarker(**marker_data)
        self.db_session.add(marker)
        await self.db_session.flush()
        return marker

    async def get_marker_by_id(self, marker_id: UUID, map_id: UUID, site_id: UUID) -> Optional[GeographicMapMarker]:
        """Get a specific marker by ID, map ID, and site ID."""
        # Convert UUIDs to strings for consistent comparison
        marker_id_str = str(marker_id)
        map_id_str = str(map_id)
        site_id_str = str(site_id)
        
        query = select(GeographicMapMarker).where(
            and_(
                or_(
                    GeographicMapMarker.id == marker_id_str,
                    GeographicMapMarker.id == marker_id_str.replace('-', '')
                ),
                or_(
                    GeographicMapMarker.map_id == map_id_str,
                    GeographicMapMarker.map_id == map_id_str.replace('-', '')
                ),
                or_(
                    GeographicMapMarker.site_id == site_id_str,
                    GeographicMapMarker.site_id == site_id_str.replace('-', '')
                )
            )
        )
        
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def delete_marker(self, marker_id: UUID) -> bool:
        """Delete a geographic map marker (CASCADE will handle photo associations)."""
        from sqlalchemy import or_
        
        # Convert UUID to string for consistent comparison
        marker_id_str = str(marker_id)
        
        # Try both with and without dashes for UUID format consistency
        stmt = delete(GeographicMapMarker).where(
            or_(
                GeographicMapMarker.id == marker_id_str,
                GeographicMapMarker.id == marker_id_str.replace('-', '')
            )
        )
        result = await self.db_session.execute(stmt)
        return result.rowcount > 0

    async def get_site_photos(self, site_id: UUID, search: Optional[str] = None,
                             skip: int = 0, limit: int = 50) -> tuple[List[Photo], int]:
        """Get photos for a site with optional search and pagination."""
        query = select(Photo).where(Photo.site_id == str(site_id))
        
        # Apply search filter
        if search:
            search_filter = or_(
                Photo.title.ilike(f"%{search}%"),
                Photo.description.ilike(f"%{search}%"),
                Photo.filename.ilike(f"%{search}%"),
                Photo.keywords.ilike(f"%{search}%")
            )
            query = query.where(search_filter)
        
        # Get total count
        count_query = select(func.count(Photo.id)).where(Photo.site_id == str(site_id))
        if search:
            count_query = count_query.where(search_filter)
        total_result = await self.db_session.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply pagination
        query = query.order_by(Photo.created_at.desc())
        query = query.offset(skip).limit(limit)
        
        result = await self.db_session.execute(query)
        photos = result.scalars().all()
        
        return photos, total

    async def delete_marker_photos(self, marker_id: UUID):
        """Delete all photo associations for a marker."""
        from sqlalchemy import or_
        
        # Convert UUID to string for consistent comparison
        marker_id_str = str(marker_id)
        
        stmt = delete(GeographicMapMarkerPhoto).where(
            or_(
                GeographicMapMarkerPhoto.marker_id == marker_id_str,
                GeographicMapMarkerPhoto.marker_id == marker_id_str.replace('-', '')
            )
        )
        await self.db_session.execute(stmt)

    async def create_marker_photo_associations(self, marker_id: UUID, photo_ids: List[UUID],
                                             created_by: UUID) -> List[GeographicMapMarkerPhoto]:
        """Create photo associations for a marker."""
        associations = []
        for i, photo_id in enumerate(photo_ids):
            association = GeographicMapMarkerPhoto(
                marker_id=str(marker_id),
                photo_id=str(photo_id),
                display_order=i,
                is_primary=(i == 0),
                created_by=str(created_by)
            )
            associations.append(association)
            self.db_session.add(association)
        
        await self.db_session.flush()
        return associations

    async def get_marker_photos(self, marker_id: UUID) -> List[Photo]:
        """Get photos associated with a marker."""
        from sqlalchemy import or_
        
        # Convert UUID to string for consistent comparison
        marker_id_str = str(marker_id)
        
        query = select(Photo).join(GeographicMapMarkerPhoto).where(
            or_(
                GeographicMapMarkerPhoto.marker_id == marker_id_str,
                GeographicMapMarkerPhoto.marker_id == marker_id_str.replace('-', '')
            )
        ).order_by(GeographicMapMarkerPhoto.display_order)
        
        result = await self.db_session.execute(query)
        return result.scalars().all()