"""Service for geographic map operations."""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sites import ArchaeologicalSite
from app.models import UserSitePermission
from app.models import User
from app.models.geographic_maps import GeographicMapMarker
from app.repositories.geographic_maps import GeographicMapRepository
from app.exceptions import BusinessLogicError
from app.services.geojson_minio_service import geojson_minio_service


class GeographicMapService:
    """Service for geographic map operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.repository = GeographicMapRepository(db_session)

    async def check_site_access(self, site_id: UUID, current_user_id: UUID) -> tuple[ArchaeologicalSite, UserSitePermission]:
        """Check if user has access to the site for geographic map operations."""
        from sqlalchemy import select, and_, or_, func
        from app.models.sites import ArchaeologicalSite
        from app.models import UserSitePermission
        
        # Check site existence
        site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
        site_result = await self.db_session.execute(site_query)
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise BusinessLogicError("Sito archeologico non trovato", 404)
        
        # Check user permissions
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
        
        permission = await self.db_session.execute(permission_query)
        permission = permission.scalar_one_or_none()
        
        if not permission:
            raise BusinessLogicError("Non hai i permessi per accedere a questo sito archeologico", 403)
        
        return site, permission

    async def get_site_maps(self, site_id: UUID, current_user_id: UUID) -> List[Dict[str, Any]]:
        """Get all geographic maps for a site."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        maps = await self.repository.get_site_maps(site_id)
        
        # Create dict manually to avoid relationship access issues
        maps_data = []
        for map_obj in maps:
            map_data = {
                "id": str(map_obj.id),
                "site_id": str(map_obj.site_id),
                "name": map_obj.name,
                "description": map_obj.description,
                "bounds": {
                    "north": map_obj.bounds_north,
                    "south": map_obj.bounds_south,
                    "east": map_obj.bounds_east,
                    "west": map_obj.bounds_west
                },
                "center": {
                    "lat": map_obj.center_lat,
                    "lng": map_obj.center_lng
                },
                "default_zoom": map_obj.default_zoom,
                "map_config": map_obj.map_config or {},
                "is_active": map_obj.is_active,
                "is_default": map_obj.is_default,
                "created_at": map_obj.created_at.isoformat() if map_obj.created_at else None,
                "updated_at": map_obj.updated_at.isoformat() if map_obj.updated_at else None,
                "layers_count": 0,  # Avoid relationship access
                "markers_count": 0 # Avoid relationship access
            }
            maps_data.append(map_data)
        
        return maps_data

    async def create_map(self, site_id: UUID, map_data: Dict[str, Any], current_user_id: UUID) -> Dict[str, Any]:
        """Create a new geographic map."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        try:
            # If it's a default map, remove the default flag from other maps
            if map_data.get('is_default', False):
                await self.repository.update_map_default_status(site_id)
            
            # Prepare map data for creation
            new_map_data = {
                "site_id": site_id,
                "name": map_data['name'],
                "description": map_data.get('description'),
                "bounds_north": map_data['bounds']['north'],
                "bounds_south": map_data['bounds']['south'],
                "bounds_east": map_data['bounds']['east'],
                "bounds_west": map_data['bounds']['west'],
                "center_lat": map_data['center']['lat'],
                "center_lng": map_data['center']['lng'],
                "default_zoom": map_data.get('default_zoom', 15),
                "map_config": map_data.get('map_config', {}),
                "is_default": map_data.get('is_default', False),
                "created_by": current_user_id
            }
            
            new_map = await self.repository.create_map(new_map_data)
            await self.db_session.commit()
            
            logger.info(f"Geographic map created: {new_map.id} for site {site_id}")
            
            # Create dict manually to avoid relationship access issues
            map_dict = {
                "id": str(new_map.id),
                "site_id": str(new_map.site_id),
                "name": new_map.name,
                "description": new_map.description,
                "bounds": {
                    "north": new_map.bounds_north,
                    "south": new_map.bounds_south,
                    "east": new_map.bounds_east,
                    "west": new_map.bounds_west
                },
                "center": {
                    "lat": new_map.center_lat,
                    "lng": new_map.center_lng
                },
                "default_zoom": new_map.default_zoom,
                "map_config": new_map.map_config or {},
                "is_active": new_map.is_active,
                "is_default": new_map.is_default,
                "created_at": new_map.created_at.isoformat() if new_map.created_at else None,
                "updated_at": new_map.updated_at.isoformat() if new_map.updated_at else None,
                "layers_count": 0,  # New map has no layers yet
                "markers_count": 0  # New map has no markers yet
            }
            
            return {
                "message": "Mappa geografica creata con successo",
                "map_id": str(new_map.id),
                "map_data": map_dict
            }
            
        except Exception as e:
            logger.error(f"Error creating geographic map: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore creazione mappa: {str(e)}", 500)

    async def get_map_details(self, site_id: UUID, map_id: UUID, current_user_id: UUID) -> Dict[str, Any]:
        """Get detailed information about a geographic map."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        map_obj = await self.repository.get_map_with_layers_and_markers(map_id, site_id)
        
        if not map_obj:
            raise BusinessLogicError("Mappa non trovata", 404)
        
        # Create dict manually to avoid relationship access issues
        map_data = {
            "id": str(map_obj.id),
            "site_id": str(map_obj.site_id),
            "name": map_obj.name,
            "description": map_obj.description,
            "bounds": {
                "north": map_obj.bounds_north,
                "south": map_obj.bounds_south,
                "east": map_obj.bounds_east,
                "west": map_obj.bounds_west
            },
            "center": {
                "lat": map_obj.center_lat,
                "lng": map_obj.center_lng
            },
            "default_zoom": map_obj.default_zoom,
            "map_config": map_obj.map_config or {},
            "is_active": map_obj.is_active,
            "is_default": map_obj.is_default,
            "created_at": map_obj.created_at.isoformat() if map_obj.created_at else None,
            "updated_at": map_obj.updated_at.isoformat() if map_obj.updated_at else None,
            "layers": [],  # Will be populated below if relationships are loaded
            "markers": [] # Will be populated below if relationships are loaded
        }
        
        # Safely add layers and markers if they were loaded with selectinload
        try:
            if hasattr(map_obj, 'geojson_layers') and map_obj.geojson_layers:
                for layer in map_obj.geojson_layers:
                    # All layers are stored in MinIO, retrieve the actual GeoJSON data from MinIO
                    try:
                        from uuid import UUID
                        layer_id = str(layer.id)
                        map_id = str(layer.map_id)
                        site_id = str(layer.site_id)
                        
                        # Extract layer ID from the MinIO URL
                        if isinstance(layer.geojson_data, dict) and 'minio_url' in layer.geojson_data:
                            # This is a reference to MinIO, retrieve actual data
                            geojson_data = await geojson_minio_service.get_geojson_layer(
                                layer_id=layer_id,
                                site_id=site_id,
                                map_id=map_id,
                                db_session=self.db_session
                            )
                            
                            # If we couldn't retrieve the data from MinIO, use a fallback
                            if geojson_data is None:
                                logger.debug(f"Could not retrieve GeoJSON data from MinIO for layer {layer_id}, using empty data")
                                geojson_data = {
                                    "type": "FeatureCollection",
                                    "features": []
                                }
                        else:
                            # Fallback: use the data directly if not stored as MinIO reference
                            geojson_data = layer.geojson_data
                        
                        layer_data = {
                            "id": str(layer.id),
                            "map_id": str(layer.map_id),
                            "site_id": str(layer.site_id),
                            "name": layer.name,
                            "description": layer.description,
                            "layer_type": layer.layer_type,
                            "geojson_data": geojson_data,
                            "features_count": layer.features_count,
                            "style_config": layer.style_config or {},
                            "is_visible": layer.is_visible,
                            "display_order": layer.display_order,
                            "bounds": {
                                "north": layer.bounds_north,
                                "south": layer.bounds_south,
                                "east": layer.bounds_east,
                                "west": layer.bounds_west
                            } if layer.bounds_north else None,
                            "created_at": layer.created_at.isoformat() if layer.created_at else None,
                            "updated_at": layer.updated_at.isoformat() if layer.updated_at else None,
                            "minio_url": layer.geojson_data.get('minio_url') if isinstance(layer.geojson_data, dict) and 'minio_url' in layer.geojson_data else None
                        }
                    except Exception as e:
                        logger.debug(f"Error retrieving GeoJSON data from MinIO for layer {layer.id}: {e}")
                        # Fallback to showing the reference with empty geojson_data
                        layer_data = {
                            "id": str(layer.id),
                            "map_id": str(layer.map_id),
                            "site_id": str(layer.site_id),
                            "name": layer.name,
                            "description": layer.description,
                            "layer_type": layer.layer_type,
                            "geojson_data": {
                                "type": "FeatureCollection",
                                "features": []
                            },  # Provide empty GeoJSON as fallback
                            "features_count": layer.features_count,
                            "style_config": layer.style_config or {},
                            "is_visible": layer.is_visible,
                            "display_order": layer.display_order,
                            "bounds": {
                                "north": layer.bounds_north,
                                "south": layer.bounds_south,
                                "east": layer.bounds_east,
                                "west": layer.bounds_west
                            } if layer.bounds_north else None,
                            "created_at": layer.created_at.isoformat() if layer.created_at else None,
                            "updated_at": layer.updated_at.isoformat() if layer.updated_at else None,
                            "minio_url": layer.geojson_data.get('minio_url') if isinstance(layer.geojson_data, dict) and 'minio_url' in layer.geojson_data else None
                        }
                    map_data["layers"].append(layer_data)
        except Exception as e:
            logger.error(f"Error processing layers in get_map_details: {e}")
            # If relationship access fails, just leave empty list
            pass
        
        try:
            if hasattr(map_obj, 'manual_markers') and map_obj.manual_markers:
                for marker in map_obj.manual_markers:
                    # Load associated photos
                    photos_list = []
                    if hasattr(marker, 'photo_associations') and marker.photo_associations:
                        for assoc in marker.photo_associations:
                            if hasattr(assoc, 'photo') and assoc.photo:
                                photo = assoc.photo
                                photos_list.append({
                                    "id": str(photo.id),
                                    "title": photo.title or photo.original_filename or photo.filename,
                                    "description": photo.description,
                                    "filename": photo.filename,
                                    "thumbnail_url": photo.thumbnail_url,
                                    "full_url": photo.full_url,
                                    "width": photo.width,
                                    "height": photo.height,
                                    "has_deep_zoom": photo.has_deep_zoom,
                                    "deep_zoom_status": photo.deepzoom_status,
                                    "display_order": assoc.display_order,
                                    "is_primary": assoc.is_primary
                                })
                    
                    marker_data = {
                        "id": str(marker.id),
                        "map_id": str(marker.map_id),
                        "site_id": str(marker.site_id),
                        "latitude": marker.latitude,
                        "longitude": marker.longitude,
                        "title": marker.title,
                        "description": marker.description,
                        "marker_type": marker.marker_type,
                        "icon": marker.icon,
                        "color": marker.color,
                        "metadata": marker.marker_metadata or {},
                        "created_at": marker.created_at.isoformat() if marker.created_at else None,
                        "updated_at": marker.updated_at.isoformat() if marker.updated_at else None,
                        "photos_count": len(photos_list),
                        "photos": photos_list
                    }
                    map_data["markers"].append(marker_data)
        except Exception as e:
            # If relationship access fails, just leave empty list
            logger.warning(f"Could not load marker photos: {e}")
            pass
        
        return map_data

    async def delete_map(self, site_id: UUID, map_id: UUID, current_user_id: UUID) -> Dict[str, str]:
        """Delete a geographic map."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        # Check if map exists
        map_obj = await self.repository.get_map_by_id(map_id, site_id)
        
        if not map_obj:
            raise BusinessLogicError("Mappa non trovata", 404)
        
        try:
            success = await self.repository.delete_map(map_id)
            if success:
                await self.db_session.commit()
                logger.info(f"Geographic map deleted: {map_id}")
                return {"message": "Mappa geografica eliminata con successo"}
            else:
                raise BusinessLogicError("Errore eliminazione mappa", 500)
                
        except Exception as e:
            logger.error(f"Error deleting geographic map: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore eliminazione mappa: {str(e)}", 500)

    async def create_layer(self, site_id: UUID, map_id: UUID, layer_data: Dict[str, Any], current_user_id: UUID) -> Dict[str, Any]:
        """Create a new GeoJSON layer in a map (always stored in MinIO)."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        try:
            # Verify map exists
            map_obj = await self.repository.get_map_by_id(map_id, site_id)
            
            if not map_obj:
                raise BusinessLogicError("Mappa non trovata", 404)
            
            # Extract bounds from GeoJSON if not provided
            geojson_data = layer_data['geojson_data']
            bounds = layer_data.get('bounds')
            
            if not bounds and geojson_data.get('features'):
                # Calculate bounds from features
                lats = []
                lngs = []
                for feature in geojson_data['features']:
                    if feature['geometry']['type'] == 'Point':
                        coords = feature['geometry']['coordinates']
                        lngs.append(coords[0])
                        lats.append(coords[1])
                
                if lats and lngs:
                    bounds = {
                        'north': max(lats),
                        'south': min(lats),
                        'east': max(lngs),
                        'west': min(lngs)
                    }
            
            # Generate layer ID first to ensure consistency between MinIO and database
            from uuid import uuid4
            layer_id = uuid4()
            
            # Prepare layer data for creation first
            layer = {
                "id": layer_id,  # Use the same ID for both MinIO and database
                "map_id": map_id,
                "site_id": site_id,
                "name": layer_data['name'],
                "description": layer_data.get('description'),
                "layer_type": layer_data.get('layer_type', 'geojson'),
                "geojson_data": {},  # Placeholder, will be updated after MinIO upload
                "features_count": len(geojson_data.get('features', [])),
                "style_config": layer_data.get('style_config', {}),
                "is_visible": layer_data.get('is_visible', True),
                "display_order": layer_data.get('display_order', 0),
                "bounds_north": bounds.get('north') if bounds else None,
                "bounds_south": bounds.get('south') if bounds else None,
                "bounds_east": bounds.get('east') if bounds else None,
                "bounds_west": bounds.get('west') if bounds else None,
                "created_by": current_user_id
            }
            
            # Store GeoJSON data in MinIO using the same layer_id
            minio_url = await geojson_minio_service.save_geojson_layer(
                geojson_data=geojson_data,
                layer_id=str(layer_id),
                site_id=str(site_id),
                map_id=str(map_id),
                layer_name=layer_data.get('name', f'Layer {layer_id}')
            )
            
            # Update layer data with MinIO reference
            layer["geojson_data"] = {"minio_url": minio_url}
            
            # Create the layer in database with the pre-generated ID
            new_layer = await self.repository.create_layer(layer)
            await self.db_session.commit()
            
            logger.info(f"GeoJSON layer saved to MinIO: {new_layer.id} for map {map_id}")
            
            # Create dict manually to avoid relationship access issues
            layer_dict = {
                "id": str(new_layer.id),
                "map_id": str(new_layer.map_id),
                "site_id": str(new_layer.site_id),
                "name": new_layer.name,
                "description": new_layer.description,
                "layer_type": new_layer.layer_type,
                "geojson_data": geojson_data,  # Include the actual data in response
                "features_count": new_layer.features_count,
                "style_config": new_layer.style_config or {},
                "is_visible": new_layer.is_visible,
                "display_order": new_layer.display_order,
                "bounds": {
                    "north": new_layer.bounds_north,
                    "south": new_layer.bounds_south,
                    "east": new_layer.bounds_east,
                    "west": new_layer.bounds_west
                } if new_layer.bounds_north else None,
                "created_at": new_layer.created_at.isoformat() if new_layer.created_at else None,
                "updated_at": new_layer.updated_at.isoformat() if new_layer.updated_at else None,
                "minio_url": minio_url
            }
            
            return {
                "message": "Layer GeoJSON salvato con successo",
                "layer_id": str(new_layer.id),
                "layer_data": layer_dict
            }
            
        except Exception as e:
            logger.error(f"Error saving GeoJSON layer: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore salvataggio layer: {str(e)}", 500)

    async def create_marker(self, site_id: UUID, map_id: UUID, marker_data: Dict[str, Any], current_user_id: UUID) -> Dict[str, Any]:
        """Create a new manual marker in a map."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        try:
            # Verify map exists
            map_obj = await self.repository.get_map_by_id(map_id, site_id)
            
            if not map_obj:
                raise BusinessLogicError("Mappa non trovata", 404)
            
            # Prepare marker data for creation
            marker = {
                "map_id": map_id,
                "site_id": site_id,
                "latitude": marker_data['latitude'],
                "longitude": marker_data['longitude'],
                "title": marker_data['title'],
                "description": marker_data.get('description'),
                "marker_type": marker_data.get('marker_type', 'generic'),
                "icon": marker_data.get('icon', '📍'),
                "color": marker_data.get('color', '#007bff'),
                "marker_metadata": marker_data.get('metadata', {}),
                "created_by": current_user_id
            }
            
            new_marker = await self.repository.create_marker(marker)
            await self.db_session.commit()
            
            logger.info(f"Manual marker saved: {new_marker.id} for map {map_id}")
            
            # Create dict manually to avoid relationship access issues
            marker_dict = {
                "id": str(new_marker.id),
                "map_id": str(new_marker.map_id),
                "site_id": str(new_marker.site_id),
                "latitude": new_marker.latitude,
                "longitude": new_marker.longitude,
                "title": new_marker.title,
                "description": new_marker.description,
                "marker_type": new_marker.marker_type,
                "icon": new_marker.icon,
                "color": new_marker.color,
                "metadata": new_marker.marker_metadata or {},
                "created_at": new_marker.created_at.isoformat() if new_marker.created_at else None,
                "updated_at": new_marker.updated_at.isoformat() if new_marker.updated_at else None,
                "photos_count": 0,  # New marker has no photos yet
                "photos": []  # New marker has no photos yet
            }
            
            return {
                "message": "Marker salvato con successo",
                "marker_id": str(new_marker.id),
                "marker_data": marker_dict
            }
            
        except Exception as e:
            logger.error(f"Error saving manual marker: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore salvataggio marker: {str(e)}", 500)

    async def delete_marker(self, site_id: UUID, map_id: UUID, marker_id: UUID, current_user_id: UUID) -> Dict[str, str]:
        """Delete a manual marker from a map."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        try:
            # First, verify marker exists with detailed diagnostics
            from sqlalchemy import select
            
            # Check if marker exists at all
            marker_check = await self.db_session.execute(
                select(GeographicMapMarker).where(GeographicMapMarker.id == marker_id)
            )
            marker_basic = marker_check.scalar_one_or_none()
            
            if not marker_basic:
                logger.warning(f"Marker not found with ID: {marker_id}")
                raise BusinessLogicError(f"Marker non trovato con ID: {marker_id}", 404)
            
            # Check if marker belongs to the correct map
            if marker_basic.map_id != map_id:
                logger.warning(f"Marker {marker_id} belongs to map {marker_basic.map_id}, not {map_id}")
                raise BusinessLogicError(f"Marker non appartiene alla mappa specificata", 400)
            
            # Check if marker belongs to the correct site
            if marker_basic.site_id != site_id:
                logger.warning(f"Marker {marker_id} belongs to site {marker_basic.site_id}, not {site_id}")
                raise BusinessLogicError(f"Marker non appartiene al sito specificato", 400)
            
            # Delete marker (CASCADE will handle photo associations)
            success = await self.repository.delete_marker(marker_id)
            if success:
                await self.db_session.commit()
                logger.info(f"Geographic marker deleted: {marker_id}")
                return {"message": "Marker eliminato con successo"}
            else:
                raise BusinessLogicError("Errore eliminazione marker", 500)
                
        except BusinessLogicError:
            # Re-raise business logic errors as-is
            await self.db_session.rollback()
            raise
        except Exception as e:
            logger.error(f"Error deleting geographic marker: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore eliminazione marker: {str(e)}", 500)

    async def associate_photos_to_marker(self, site_id: UUID, map_id: UUID, marker_id: UUID,
                                       photo_ids: List[UUID], current_user_id: UUID) -> Dict[str, int]:
        """Associate photos to a geographic marker."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        try:
            # Verify marker exists
            marker = await self.repository.get_marker_by_id(marker_id, map_id, site_id)
            
            if not marker:
                raise BusinessLogicError("Marker non trovato", 404)
            
            # Verify that the photos exist and belong to the site
            from sqlalchemy import select, and_
            from app.models import Photo
            photos_query = select(Photo).where(
                and_(
                    Photo.id.in_(photo_ids),
                    Photo.site_id == site_id
                )
            )
            photos_result = await self.db_session.execute(photos_query)
            photos = photos_result.scalars().all()
            
            if len(photos) != len(photo_ids):
                raise BusinessLogicError("Alcune foto non esistono o non appartengono al sito", 400)
            
            # Remove existing associations
            await self.repository.delete_marker_photos(marker_id)
            
            # Create new associations
            associations = await self.repository.create_marker_photo_associations(marker_id, photo_ids, current_user_id)
            await self.db_session.commit()
            
            logger.info(f"Photos associated to marker {marker_id}: {len(associations)} photos")
            
            return {
                "message": f"Associate {len(associations)} foto al marker",
                "associations_count": len(associations)
            }
            
        except Exception as e:
            logger.error(f"Error associating photos to marker: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore associazione foto: {str(e)}", 500)

    async def get_site_photos_for_association(self, site_id: UUID, current_user_id: UUID, 
                                            search: Optional[str] = None, page: int = 1, 
                                            limit: int = 50) -> Dict[str, Any]:
        """Get site photos for association to markers."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        skip = (page - 1) * limit
        photos, total = await self.repository.get_site_photos(site_id, search, skip, limit)
        
        # Create dict manually to avoid relationship access issues
        photos_data = []
        for photo in photos:
            photo_data = {
                "id": str(photo.id),
                "site_id": str(photo.site_id),
                "title": photo.title or photo.original_filename or photo.filename,
                "description": photo.description,
                "filename": photo.filename,
                "original_filename": photo.original_filename,
                "file_path": photo.filepath,
                "file_size": photo.file_size,
                "mime_type": photo.mime_type,
                "keywords": photo.keywords,
                "width": photo.width,
                "height": photo.height,
                "created": photo.created.isoformat() if photo.created else None,
                "upload_date": photo.created.isoformat() if photo.created else None,
                "uploaded_by": str(photo.uploaded_by) if photo.uploaded_by else None,
                # URL delle immagini necessarie per la visualizzazione
                "thumbnail_url": photo.thumbnail_url,
                "full_url": photo.full_url,
                "resolution": f"{photo.width}x{photo.height}" if photo.width and photo.height else None
            }
            photos_data.append(photo_data)
        
        return {
            "site_id": str(site_id),
            "photos": photos_data,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit
        }