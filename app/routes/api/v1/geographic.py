"""
API v1 - Geographic Maps Management
Endpoints per gestione mappe geografiche archeologiche.
Implementa backward compatibility con avvisi di deprecazione.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from uuid import UUID
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

# Dependencies
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.database.session import get_async_session
from app.services.geographic_maps import GeographicMapService
from app.exceptions import BusinessLogicError

router = APIRouter()

def get_geographic_map_service(db: AsyncSession = Depends(get_async_session)) -> GeographicMapService:
    """Dependency to get geographic map service instance."""
    return GeographicMapService(db)

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifica accesso al sito e restituisce informazioni sul sito"""
    # Convert site_id to string for comparison
    site_id_str = str(site_id)
    
    # Try exact match first
    site_info = next(
        (site for site in user_sites if site["id"] == site_id_str),
        None
    )
    
    # If not found, try with UUID format normalization (remove dashes)
    if not site_info:
        site_id_no_dashes = site_id_str.replace('-', '')
        site_info = next(
            (site for site in user_sites if site["id"].replace('-', '') == site_id_no_dashes),
            None
        )
    
    if not site_info:
        # Debug logging to help troubleshoot
        logger.error(f"Site access verification failed for site_id: {site_id_str}")
        logger.error(f"Available sites for user: {[site['id'] for site in user_sites]}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sito archeologico non trovato : {site_id_str}"
        )
    
    return site_info

# Request Models
class PhotoAssociationRequest(BaseModel):
    photo_ids: List[UUID]

# === GESTIONE MAPPE GEOGRAFICHE ===

@router.get("/sites/{site_id}/maps", summary="Lista mappe geografiche", tags=["Geographic Maps"])
async def v1_get_site_geographic_maps(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Recupera tutte le mappe geografiche di un sito.
    """
    try:
        result = await geographic_map_service.get_site_maps(site_id, current_user_id)
        return JSONResponse({
            "site_id": str(site_id),
            "maps": result,
            "total": len(result)
        })
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.post("/sites/{site_id}/maps", summary="Crea mappa geografica", tags=["Geographic Maps"])
async def v1_create_geographic_map(
    site_id: UUID,
    map_data: dict,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Crea una nuova mappa geografica.
    """
    try:
        result = await geographic_map_service.create_map(site_id, map_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.get("/sites/{site_id}/maps/{map_id}", summary="Dettagli mappa geografica", tags=["Geographic Maps"])
async def v1_get_geographic_map_details(
    site_id: UUID,
    map_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Ottieni dettagli completi di una mappa geografica.
    """
    try:
        result = await geographic_map_service.get_map_details(site_id, map_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.delete("/sites/{site_id}/maps/{map_id}", summary="Elimina mappa geografica", tags=["Geographic Maps"])
async def v1_delete_geographic_map(
    site_id: UUID,
    map_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Elimina una mappa geografica.
    """
    try:
        result = await geographic_map_service.delete_map(site_id, map_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

# === GESTIONE LAYER GEOJSON ===

@router.post("/sites/{site_id}/maps/{map_id}/layers", summary="Crea layer GeoJSON", tags=["Geographic Maps - Layers"])
async def v1_save_geojson_layer(
    site_id: UUID,
    map_id: UUID,
    layer_data: dict,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Salva un layer GeoJSON nella mappa (sempre su MinIO).
    """
    try:
        result = await geographic_map_service.create_layer(site_id, map_id, layer_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

# === GESTIONE MARKER MANUALI ===

@router.post("/sites/{site_id}/maps/{map_id}/markers", summary="Crea marker manuale", tags=["Geographic Maps - Markers"])
async def v1_save_manual_marker(
    site_id: UUID,
    map_id: UUID,
    marker_data: dict,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Salva un marker manuale nella mappa.
    """
    try:
        result = await geographic_map_service.create_marker(site_id, map_id, marker_data, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.delete("/sites/{site_id}/maps/{map_id}/markers/{marker_id}", summary="Elimina marker manuale", tags=["Geographic Maps - Markers"])
async def v1_delete_manual_marker(
    site_id: UUID,
    map_id: UUID,
    marker_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Elimina un marker manuale dalla mappa.
    """
    try:
        result = await geographic_map_service.delete_marker(site_id, map_id, marker_id, current_user_id)
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

# === GESTIONE ASSOCIAZIONI FOTO ===

@router.post("/sites/{site_id}/maps/{map_id}/markers/{marker_id}/photos", summary="Associa foto a marker", tags=["Geographic Maps - Photos"])
async def v1_associate_photos_to_marker(
    site_id: UUID,
    map_id: UUID,
    marker_id: UUID,
    request: PhotoAssociationRequest,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Associa foto a un marker geografico.
    """
    try:
        result = await geographic_map_service.associate_photos_to_marker(
            site_id, map_id, marker_id, request.photo_ids, current_user_id
        )
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.get("/sites/{site_id}/photos", summary="Foto del sito per associazione", tags=["Geographic Maps - Photos"])
async def v1_get_site_photos_for_association(
    site_id: UUID,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist),
    geographic_map_service: GeographicMapService = Depends(get_geographic_map_service)
):
    """
    Ottieni foto del sito per associazione ai marker.
    """
    # Verifica accesso al sito prima di chiamare il servizio
    verify_site_access(site_id, user_sites)
    
    try:
        result = await geographic_map_service.get_site_photos_for_association(
            site_id, current_user_id, search, page, limit
        )
        return result
    except BusinessLogicError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

# MIGRATION HELPER

@router.get("/migration/help", summary="Aiuto migrazione API geographic maps", tags=["Geographic Maps - Migration"])
async def migration_help():
    """
    Fornisce informazioni sulla migrazione dalla vecchia alla nuova API structure per geographic maps.
    """
    return {
        "migration_guide": {
            "old_endpoints": {
                "/api/geographic-maps/site/{site_id}/maps": "/api/v1/geographic/sites/{site_id}/maps",
                "/api/geographic-maps/site/{site_id}/maps/{map_id}": "/api/v1/geographic/sites/{site_id}/maps/{map_id}",
                "/api/geographic-maps/site/{site_id}/maps/{map_id}/layers": "/api/v1/geographic/sites/{site_id}/maps/{map_id}/layers",
                "/api/geographic-maps/site/{site_id}/maps/{map_id}/markers": "/api/v1/geographic/sites/{site_id}/maps/{map_id}/markers",
                "/api/geographic-maps/site/{site_id}/maps/{map_id}/markers/{marker_id}": "/api/v1/geographic/sites/{site_id}/maps/{map_id}/markers/{marker_id}",
                "/api/geographic-maps/site/{site_id}/maps/{map_id}/markers/{marker_id}/photos": "/api/v1/geographic/sites/{site_id}/maps/{map_id}/markers/{marker_id}/photos",
                "/api/geographic-maps/site/{site_id}/photos": "/api/v1/geographic/sites/{site_id}/photos"
            },
            "changes": [
                "Standardizzazione URL patterns",
                "Agregazione endpoints geographic maps in dominio unico",
                "Headers di deprecazione automatici",
                "Documentazione migliorata",
                "Implementazione completa di tutti gli endpoint"
            ],
            "deadline": "2025-12-31",
            "action_required": "Aggiornare client applications per usare nuovi endpoints geographic maps v1"
        }
    }