# app/routes/api/geographic_maps.py - API per gestione mappe geografiche

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.services.geographic_maps import GeographicMapService
from app.exceptions import BusinessLogicError


def get_geographic_map_service(db: AsyncSession = Depends(get_async_session)) -> GeographicMapService:
    """Dependency to get geographic map service instance."""
    return GeographicMapService(db)


geographic_maps_router = APIRouter(prefix="/api/geographic-maps", tags=["geographic_maps"])


# === GESTIONE MAPPE GEOGRAFICHE ===

@geographic_maps_router.get("/sites/{site_id}/maps")
async def get_site_geographic_maps(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Ottieni tutte le mappe geografiche di un sito"""
    try:
        result = await geographic_map_service.get_site_maps(site_id, current_user_id)
        return JSONResponse({
            "site_id": str(site_id),
            "maps": result,
            "total": len(result)
        })
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@geographic_maps_router.post("/sites/{site_id}/maps")
async def create_geographic_map(
    site_id: UUID,
    map_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Crea una nuova mappa geografica"""
    try:
        result = await geographic_map_service.create_map(site_id, map_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@geographic_maps_router.get("/sites/{site_id}/maps/{map_id}")
async def get_geographic_map_details(
    site_id: UUID,
    map_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Ottieni dettagli completi di una mappa geografica"""
    try:
        result = await geographic_map_service.get_map_details(site_id, map_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@geographic_maps_router.delete("/sites/{site_id}/maps/{map_id}")
async def delete_geographic_map(
    site_id: UUID,
    map_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Elimina una mappa geografica"""
    try:
        result = await geographic_map_service.delete_map(site_id, map_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# === GESTIONE LAYER GEOJSON ===

@geographic_maps_router.post("/sites/{site_id}/maps/{map_id}/layers")
async def save_geojson_layer(
    site_id: UUID,
    map_id: UUID,
    layer_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Salva un layer GeoJSON nella mappa"""
    try:
        result = await geographic_map_service.create_layer(site_id, map_id, layer_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# === GESTIONE MARKER MANUALI ===

@geographic_maps_router.post("/sites/{site_id}/maps/{map_id}/markers")
async def save_manual_marker(
    site_id: UUID,
    map_id: UUID,
    marker_data: dict,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Salva un marker manuale nella mappa"""
    try:
        result = await geographic_map_service.create_marker(site_id, map_id, marker_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@geographic_maps_router.delete("/sites/{site_id}/maps/{map_id}/markers/{marker_id}")
async def delete_manual_marker(
    site_id: UUID,
    map_id: UUID,
    marker_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Elimina un marker manuale dalla mappa"""
    try:
        result = await geographic_map_service.delete_marker(site_id, map_id, marker_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


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
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Associa foto a un marker geografico"""
    try:
        result = await geographic_map_service.associate_photos_to_marker(
            site_id, map_id, marker_id, request.photo_ids, current_user_id
        )
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@geographic_maps_router.get("/sites/{site_id}/photos")
async def get_site_photos_for_association(
    site_id: UUID,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user_id: UUID = Depends(get_current_user_id),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """Ottieni foto del sito per associazione ai marker"""
    try:
        result = await geographic_map_service.get_site_photos_for_association(
            site_id, current_user_id, search, page, limit
        )
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)