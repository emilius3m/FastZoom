# app/routes/api/geographic_maps.py - API per gestione mappe geografiche

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, delete
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.geographic_maps import GeographicMap, GeographicMapLayer, GeographicMapMarker, GeographicMapMarkerPhoto
from app.models.photos import Photo
from app.models.users import User

geographic_maps_router = APIRouter(prefix="/api/geographic-maps", tags=["geographic_maps"])

async def get_site_access_for_maps(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito per operazioni su mappe geografiche"""
    
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

# === GESTIONE MAPPE GEOGRAFICHE ===

@geographic_maps_router.get("/sites/{site_id}/maps")
async def get_site_geographic_maps(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_maps),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni tutte le mappe geografiche di un sito"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query mappe del sito
    maps_query = select(GeographicMap).where(
        and_(
            GeographicMap.site_id == site_id,
            GeographicMap.is_active == True
        )
    ).order_by(GeographicMap.is_default.desc(), GeographicMap.created_at.desc())
    
    maps = await db.execute(maps_query)
    maps = maps.scalars().all()
    
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
            "markers_count": 0  # Avoid relationship access
        }
        maps_data.append(map_data)
    
    return JSONResponse({
        "site_id": str(site_id),
        "maps": maps_data,
        "total": len(maps_data)
    })

@geographic_maps_router.post("/sites/{site_id}/maps")
async def create_geographic_map(
    site_id: UUID,
    map_data: dict,
    site_access: tuple = Depends(get_site_access_for_maps),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea una nuova mappa geografica"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Se è mappa di default, rimuovi flag da altre mappe
        if map_data.get('is_default', False):
            # Use proper SQLAlchemy async update syntax
            await db.execute(
                GeographicMap.__table__.update().where(
                    and_(
                        GeographicMap.site_id == site_id,
                        GeographicMap.is_default == True
                    )
                ).values(is_default=False)
            )
        
        # Crea mappa
        new_map = GeographicMap(
            site_id=site_id,
            name=map_data['name'],
            description=map_data.get('description'),
            bounds_north=map_data['bounds']['north'],
            bounds_south=map_data['bounds']['south'],
            bounds_east=map_data['bounds']['east'],
            bounds_west=map_data['bounds']['west'],
            center_lat=map_data['center']['lat'],
            center_lng=map_data['center']['lng'],
            default_zoom=map_data.get('default_zoom', 15),
            map_config=map_data.get('map_config', {}),
            is_default=map_data.get('is_default', False),
            created_by=current_user_id
        )
        
        db.add(new_map)
        await db.commit()
        await db.refresh(new_map)
        
        logger.info(f"Geographic map created: {new_map.id} for site {site_id}")
        
        # Create dict manually to avoid relationship access issues
        map_data = {
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
        
        return JSONResponse({
            "message": "Mappa geografica creata con successo",
            "map_id": str(new_map.id),
            "map_data": map_data
        })
        
    except Exception as e:
        logger.error(f"Error creating geographic map: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione mappa: {str(e)}")

@geographic_maps_router.get("/sites/{site_id}/maps/{map_id}")
async def get_geographic_map_details(
    site_id: UUID,
    map_id: UUID,
    site_access: tuple = Depends(get_site_access_for_maps),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni dettagli completi di una mappa geografica"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query mappa con layer e marker
    map_query = select(GeographicMap).options(
        selectinload(GeographicMap.geojson_layers),
        selectinload(GeographicMap.manual_markers).selectinload(GeographicMapMarker.photo_associations)
    ).where(
        and_(
            GeographicMap.id == map_id,
            GeographicMap.site_id == site_id
        )
    )
    
    map_obj = await db.execute(map_query)
    map_obj = map_obj.scalar_one_or_none()
    
    if not map_obj:
        raise HTTPException(status_code=404, detail="Mappa non trovata")
    
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
        "markers": []  # Will be populated below if relationships are loaded
    }
    
    # Safely add layers and markers if they were loaded with selectinload
    try:
        if hasattr(map_obj, 'geojson_layers') and map_obj.geojson_layers:
            for layer in map_obj.geojson_layers:
                layer_data = {
                    "id": str(layer.id),
                    "map_id": str(layer.map_id),
                    "site_id": str(layer.site_id),
                    "name": layer.name,
                    "description": layer.description,
                    "layer_type": layer.layer_type,
                    "geojson_data": layer.geojson_data,
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
                    "updated_at": layer.updated_at.isoformat() if layer.updated_at else None
                }
                map_data["layers"].append(layer_data)
    except Exception:
        # If relationship access fails, just leave empty list
        pass
    
    try:
        if hasattr(map_obj, 'manual_markers') and map_obj.manual_markers:
            for marker in map_obj.manual_markers:
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
                    "photos_count": 0,  # Avoid further relationship access
                    "photos": []  # Avoid further relationship access
                }
                map_data["markers"].append(marker_data)
    except Exception:
        # If relationship access fails, just leave empty list
        pass
    
    return JSONResponse(map_data)

@geographic_maps_router.delete("/sites/{site_id}/maps/{map_id}")
async def delete_geographic_map(
    site_id: UUID,
    map_id: UUID,
    site_access: tuple = Depends(get_site_access_for_maps),
    db: AsyncSession = Depends(get_async_session)
):
    """Elimina una mappa geografica"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    # Trova mappa
    map_obj = await db.execute(
        select(GeographicMap).where(
            and_(
                GeographicMap.id == map_id,
                GeographicMap.site_id == site_id
            )
        )
    )
    map_obj = map_obj.scalar_one_or_none()
    
    if not map_obj:
        raise HTTPException(status_code=404, detail="Mappa non trovata")
    
    try:
        # Elimina mappa (CASCADE eliminerà layer e marker)
        await db.execute(
            delete(GeographicMap).where(GeographicMap.id == map_id)
        )
        await db.commit()
        
        logger.info(f"Geographic map deleted: {map_id}")
        
        return JSONResponse({
            "message": "Mappa geografica eliminata con successo"
        })
        
    except Exception as e:
        logger.error(f"Error deleting geographic map: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore eliminazione mappa: {str(e)}")

# === GESTIONE LAYER GEOJSON ===

@geographic_maps_router.post("/sites/{site_id}/maps/{map_id}/layers")
async def save_geojson_layer(
    site_id: UUID,
    map_id: UUID,
    layer_data: dict,
    site_access: tuple = Depends(get_site_access_for_maps),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Salva un layer GeoJSON nella mappa"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Verifica esistenza mappa
        map_obj = await db.execute(
            select(GeographicMap).where(
                and_(
                    GeographicMap.id == map_id,
                    GeographicMap.site_id == site_id
                )
            )
        )
        map_obj = map_obj.scalar_one_or_none()
        
        if not map_obj:
            raise HTTPException(status_code=404, detail="Mappa non trovata")
        
        # Estrai bounds dal GeoJSON se non forniti
        geojson_data = layer_data['geojson_data']
        bounds = layer_data.get('bounds')
        
        if not bounds and geojson_data.get('features'):
            # Calcola bounds dalle feature
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
        
        # Crea layer
        layer = GeographicMapLayer(
            map_id=map_id,
            site_id=site_id,
            name=layer_data['name'],
            description=layer_data.get('description'),
            layer_type=layer_data.get('layer_type', 'geojson'),
            geojson_data=geojson_data,
            features_count=len(geojson_data.get('features', [])),
            style_config=layer_data.get('style_config', {}),
            is_visible=layer_data.get('is_visible', True),
            display_order=layer_data.get('display_order', 0),
            bounds_north=bounds.get('north') if bounds else None,
            bounds_south=bounds.get('south') if bounds else None,
            bounds_east=bounds.get('east') if bounds else None,
            bounds_west=bounds.get('west') if bounds else None,
            created_by=current_user_id
        )
        
        db.add(layer)
        await db.commit()
        await db.refresh(layer)
        
        logger.info(f"GeoJSON layer saved: {layer.id} for map {map_id}")
        
        # Create dict manually to avoid relationship access issues
        layer_data = {
            "id": str(layer.id),
            "map_id": str(layer.map_id),
            "site_id": str(layer.site_id),
            "name": layer.name,
            "description": layer.description,
            "layer_type": layer.layer_type,
            "geojson_data": layer.geojson_data,
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
            "updated_at": layer.updated_at.isoformat() if layer.updated_at else None
        }
        
        return JSONResponse({
            "message": "Layer GeoJSON salvato con successo",
            "layer_id": str(layer.id),
            "layer_data": layer_data
        })
        
    except Exception as e:
        logger.error(f"Error saving GeoJSON layer: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore salvataggio layer: {str(e)}")

# === GESTIONE MARKER MANUALI ===

@geographic_maps_router.post("/sites/{site_id}/maps/{map_id}/markers")
async def save_manual_marker(
    site_id: UUID,
    map_id: UUID,
    marker_data: dict,
    site_access: tuple = Depends(get_site_access_for_maps),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Salva un marker manuale nella mappa"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Verifica esistenza mappa
        map_obj = await db.execute(
            select(GeographicMap).where(
                and_(
                    GeographicMap.id == map_id,
                    GeographicMap.site_id == site_id
                )
            )
        )
        map_obj = map_obj.scalar_one_or_none()
        
        if not map_obj:
            raise HTTPException(status_code=404, detail="Mappa non trovata")
        
        # Crea marker
        marker = GeographicMapMarker(
            map_id=map_id,
            site_id=site_id,
            latitude=marker_data['latitude'],
            longitude=marker_data['longitude'],
            title=marker_data['title'],
            description=marker_data.get('description'),
            marker_type=marker_data.get('marker_type', 'generic'),
            icon=marker_data.get('icon', '📍'),
            color=marker_data.get('color', '#007bff'),
            marker_metadata=marker_data.get('metadata', {}),
            created_by=current_user_id
        )
        
        db.add(marker)
        await db.commit()
        await db.refresh(marker)
        
        logger.info(f"Manual marker saved: {marker.id} for map {map_id}")
        
        # Create dict manually to avoid relationship access issues
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
            "photos_count": 0,  # New marker has no photos yet
            "photos": []  # New marker has no photos yet
        }
        
        return JSONResponse({
            "message": "Marker salvato con successo",
            "marker_id": str(marker.id),
            "marker_data": marker_data
        })
        
    except Exception as e:
        logger.error(f"Error saving manual marker: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore salvataggio marker: {str(e)}")

# === GESTIONE ASSOCIAZIONI FOTO ===

from pydantic import BaseModel

class PhotoAssociationRequest(BaseModel):
    photo_ids: List[UUID]

@geographic_maps_router.post("/sites/{site_id}/maps/{map_id}/markers/{marker_id}/photos")
async def associate_photos_to_marker(
    site_id: UUID,
    map_id: UUID,
    marker_id: UUID,
    request: PhotoAssociationRequest,
    site_access: tuple = Depends(get_site_access_for_maps),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Associa foto a un marker geografico"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Verifica esistenza marker
        marker = await db.execute(
            select(GeographicMapMarker).where(
                and_(
                    GeographicMapMarker.id == marker_id,
                    GeographicMapMarker.map_id == map_id,
                    GeographicMapMarker.site_id == site_id
                )
            )
        )
        marker = marker.scalar_one_or_none()
        
        if not marker:
            raise HTTPException(status_code=404, detail="Marker non trovato")
        
        # Verifica che le foto esistano e appartengano al sito
        photos = await db.execute(
            select(Photo).where(
                and_(
                    Photo.id.in_(request.photo_ids),
                    Photo.site_id == site_id
                )
            )
        )
        photos = photos.scalars().all()
        
        if len(photos) != len(request.photo_ids):
            raise HTTPException(status_code=400, detail="Alcune foto non esistono o non appartengono al sito")
        
        # Rimuovi associazioni esistenti
        await db.execute(
            delete(GeographicMapMarkerPhoto).where(
                GeographicMapMarkerPhoto.marker_id == marker_id
            )
        )
        
        # Crea nuove associazioni
        associations = []
        for i, photo in enumerate(photos):
            association = GeographicMapMarkerPhoto(
                marker_id=marker_id,
                photo_id=photo.id,
                display_order=i,
                is_primary=(i == 0),  # Prima foto è primaria
                created_by=current_user_id
            )
            associations.append(association)
            db.add(association)
        
        await db.commit()
        
        logger.info(f"Photos associated to marker {marker_id}: {len(associations)} photos")
        
        return JSONResponse({
            "message": f"Associate {len(associations)} foto al marker",
            "associations_count": len(associations)
        })
        
    except Exception as e:
        logger.error(f"Error associating photos to marker: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore associazione foto: {str(e)}")

@geographic_maps_router.get("/sites/{site_id}/photos")
async def get_site_photos_for_association(
    site_id: UUID,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    site_access: tuple = Depends(get_site_access_for_maps),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni foto del sito per associazione ai marker"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query foto del sito
    photos_query = select(Photo).where(Photo.site_id == site_id)
    
    # Filtro ricerca
    if search:
        search_filter = or_(
            Photo.title.ilike(f"%{search}%"),
            Photo.description.ilike(f"%{search}%"),
            Photo.filename.ilike(f"%{search}%"),
            Photo.keywords.ilike(f"%{search}%")
        )
        photos_query = photos_query.where(search_filter)
    
    # Paginazione
    photos_query = photos_query.order_by(Photo.created.desc())
    photos_query = photos_query.offset((page - 1) * limit).limit(limit)
    
    photos = await db.execute(photos_query)
    photos = photos.scalars().all()
    
    # Conta totale per paginazione
    count_query = select(func.count(Photo.id)).where(Photo.site_id == site_id)
    if search:
        count_query = count_query.where(search_filter)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Create dict manually to avoid relationship access issues
    photos_data = []
    for photo in photos:
        photo_data = {
            "id": str(photo.id),
            "site_id": str(photo.site_id),
            "title": photo.title,
            "description": photo.description,
            "filename": photo.filename,
            "file_path": photo.file_path,
            "file_size": photo.file_size,
            "mime_type": photo.mime_type,
            "keywords": photo.keywords,
            "created": photo.created.isoformat() if photo.created else None,
            "uploaded_by": str(photo.uploaded_by) if photo.uploaded_by else None
        }
        photos_data.append(photo_data)
    
    return JSONResponse({
        "site_id": str(site_id),
        "photos": photos_data,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    })