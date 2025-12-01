# app/routes/api/v1/harris_matrix.py - Harris Matrix API v1 endpoints

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, Optional
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.services.harris_matrix_service import HarrisMatrixService
from sqlalchemy import select, and_

router = APIRouter()


async def verify_site_access(site_id: UUID, user_sites: list) -> bool:
    """Verify if user has access to the specified site"""
    return any(s["site_id"] == str(site_id) for s in user_sites)


@router.get(
    "/sites/{site_id}",
    summary="Generate complete Harris Matrix for a site",
    tags=["Harris Matrix"]
)
async def v1_generate_harris_matrix(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Generate complete Harris Matrix for a site.
    
    This endpoint queries all US and USM units for the specified site,
    extracts stratigraphic relationships from sequenza_fisica JSON fields,
    and returns a graph structure suitable for Cytoscape.js visualization.
    
    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        Dictionary containing nodes, edges, levels, and metadata for the Harris Matrix
    """
    try:
        logger.info(f"Generating Harris Matrix for site_id: {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Initialize service and generate matrix
        harris_service = HarrisMatrixService(db)
        matrix_data = await harris_service.generate_harris_matrix(site_id)
        
        logger.info(f"Harris Matrix generated successfully for site {site_id}")
        return JSONResponse(
            status_code=200,
            content=matrix_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Harris Matrix for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/sites/{site_id}/units/{unit_code}",
    summary="Get relationships for a specific US/USM unit",
    tags=["Harris Matrix"]
)
async def v1_get_unit_relationships(
    site_id: UUID,
    unit_code: str,
    unit_type: Optional[str] = Query("us", description="Unit type: 'us' or 'usm'"),
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Get relationships for a specific US/USM unit.
    
    This endpoint extracts all relationships defined in the sequenza_fisica
    JSON field for a specific unit, providing detailed information about
    its stratigraphic connections.
    
    Args:
        site_id: UUID of the archaeological site
        unit_code: Code of the unit (e.g., "001" for US001)
        unit_type: Type of unit ('us' or 'usm')
        
    Returns:
        Dictionary containing unit information and its relationships
    """
    try:
        logger.info(f"Getting relationships for {unit_type.upper()}{unit_code} in site {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Validate unit_type
        if unit_type not in ['us', 'usm']:
            raise HTTPException(
                status_code=400,
                detail="unit_type must be 'us' or 'usm'"
            )
        
        # Find the unit by code and site
        if unit_type == 'us':
            from app.models.stratigraphy import UnitaStratigrafica
            query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.us_code == unit_code,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
        else:  # usm
            from app.models.stratigraphy import UnitaStratigraficaMuraria
            query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.usm_code == unit_code,
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
        
        result = await db.execute(query)
        unit = result.scalar_one_or_none()
        
        if not unit:
            raise HTTPException(
                status_code=404,
                detail=f"{unit_type.upper()}{unit_code} not found in this site"
            )
        
        # Get relationships using the service
        harris_service = HarrisMatrixService(db)
        relationships = await harris_service.get_unit_relationships(
            unit_id=UUID(unit.id),
            unit_type=unit_type
        )
        
        logger.info(f"Retrieved relationships for {unit_type.upper()}{unit_code}")
        return JSONResponse(
            status_code=200,
            content=relationships
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting relationships for {unit_type}{unit_code}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get(
    "/sites/{site_id}/statistics",
    summary="Get Harris Matrix statistics for a site",
    tags=["Harris Matrix"]
)
async def v1_get_matrix_statistics(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Get summary statistics about the Harris Matrix for a site.
    
    This endpoint provides statistical information about the stratigraphic
    units and their relationships, useful for dashboard displays and
    analysis tools.
    
    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        Dictionary containing statistics about the matrix
    """
    try:
        logger.info(f"Getting Harris Matrix statistics for site_id: {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Generate the matrix to get statistics
        harris_service = HarrisMatrixService(db)
        matrix_data = await harris_service.generate_harris_matrix(site_id)
        
        # Extract statistics
        metadata = matrix_data.get('metadata', {})
        nodes = matrix_data.get('nodes', [])
        edges = matrix_data.get('edges', [])
        levels = matrix_data.get('levels', {})
        
        # Calculate additional statistics
        us_nodes = [n for n in nodes if n['type'] == 'us']
        usm_nodes = [n for n in nodes if n['type'] == 'usm']
        
        # US positive/negative statistics
        us_positive = [n for n in us_nodes if n.get('tipo') == 'positiva']
        us_negative = [n for n in us_nodes if n.get('tipo') == 'negativa']
        
        # Relationship type statistics
        relationship_types = {}
        for edge in edges:
            rel_type = edge.get('type', 'unknown')
            relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1
        
        # Level distribution
        level_distribution = {}
        for node_id, level in levels.items():
            level_distribution[level] = level_distribution.get(level, 0) + 1
        
        statistics = {
            "site_id": str(site_id),
            "units": {
                "total_us": len(us_nodes),
                "us_positive": len(us_positive),
                "us_negative": len(us_negative),
                "total_usm": len(usm_nodes),
                "total_units": len(nodes)
            },
            "relationships": {
                "total_edges": len(edges),
                "relationship_types": relationship_types
            },
            "chronology": {
                "total_levels": len(level_distribution),
                "level_distribution": level_distribution,
                "max_depth": max(level_distribution.keys()) if level_distribution else 0
            },
            "metadata": metadata
        }
        
        logger.info(f"Harris Matrix statistics retrieved for site {site_id}")
        return JSONResponse(
            status_code=200,
            content=statistics
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Harris Matrix statistics for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )