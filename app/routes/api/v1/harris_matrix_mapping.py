# app/routes/api/v1/harris_matrix_mapping.py - Mapping management endpoints

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, Optional, List
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.services.harris_matrix_mapping_service import HarrisMatrixMappingService

router = APIRouter()


async def verify_site_access(site_id: UUID, user_sites: list) -> bool:
    """Verify if user has access to the specified site"""
    return any(s["site_id"] == str(site_id) for s in user_sites)


@router.get(
    "/sites/{site_id}/mapping/recover/{session_id}",
    summary="Recover session mappings for interrupted operations",
    tags=["Harris Matrix Mapping"]
)
async def v1_recover_session_mappings(
    site_id: UUID,
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Recover session mappings for interrupted operations.
    
    This endpoint allows recovery of mapping data from interrupted
    Harris Matrix operations, providing information about the session
    status and recoverable mappings.
    
    Args:
        site_id: UUID of the archaeological site
        session_id: Session identifier to recover
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Dictionary with recovery information and mappings
        
    Raises:
        HTTPException: If site access is denied or recovery fails
    """
    try:
        logger.info(f"Recovering session mappings for site_id: {site_id}, session_id: {session_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access denied to this site",
                    "field": "site_id",
                    "value": str(site_id),
                    "suggestion": "Verify you have access to this site"
                }
            )
        
        # Initialize mapping service
        mapping_service = HarrisMatrixMappingService(db)
        
        # Attempt to recover session
        recovery_result = await mapping_service.recover_session(site_id, session_id)
        
        logger.success(f"Session recovery completed for session {session_id}")
        return recovery_result
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error recovering session {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to recover session mappings",
                "type": "recovery_error",
                "details": str(e),
                "suggestion": "Please check the session ID and try again"
            }
        )


@router.get(
    "/sites/{site_id}/mapping/stats/{session_id}",
    summary="Get statistics for a mapping session",
    tags=["Harris Matrix Mapping"]
)
async def v1_get_session_statistics(
    site_id: UUID,
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Get statistics for a mapping session.
    
    This endpoint provides detailed statistics about mappings in a session,
    including counts by status and timing information.
    
    Args:
        site_id: UUID of the archaeological site
        session_id: Session identifier
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Dictionary with session statistics
        
    Raises:
        HTTPException: If site access is denied or stats retrieval fails
    """
    try:
        logger.info(f"Getting session statistics for site_id: {site_id}, session_id: {session_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access denied to this site",
                    "field": "site_id",
                    "value": str(site_id),
                    "suggestion": "Verify you have access to this site"
                }
            )
        
        # Initialize mapping service
        mapping_service = HarrisMatrixMappingService(db)
        
        # Get session statistics
        stats = await mapping_service.get_session_statistics(site_id, session_id)
        
        logger.success(f"Session statistics retrieved for session {session_id}")
        return stats
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error getting session statistics for {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to retrieve session statistics",
                "type": "stats_error",
                "details": str(e),
                "suggestion": "Please check the session ID and try again"
            }
        )


@router.get(
    "/sites/{site_id}/mapping/stats",
    summary="Get site-wide mapping statistics",
    tags=["Harris Matrix Mapping"]
)
async def v1_get_site_mapping_statistics(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Get site-wide mapping statistics.
    
    This endpoint provides comprehensive statistics about all mappings
    for a site, including counts by status and usage patterns.
    
    Args:
        site_id: UUID of the archaeological site
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Dictionary with site-wide statistics
        
    Raises:
        HTTPException: If site access is denied or stats retrieval fails
    """
    try:
        logger.info(f"Getting site mapping statistics for site_id: {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access denied to this site",
                    "field": "site_id",
                    "value": str(site_id),
                    "suggestion": "Verify you have access to this site"
                }
            )
        
        # Initialize mapping service
        mapping_service = HarrisMatrixMappingService(db)
        
        # Get site statistics
        stats = await mapping_service.get_site_mapping_statistics(site_id)
        
        logger.success(f"Site mapping statistics retrieved for site {site_id}")
        return stats
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error getting site mapping statistics for {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to retrieve site mapping statistics",
                "type": "stats_error",
                "details": str(e),
                "suggestion": "Please check the site ID and try again"
            }
        )


@router.post(
    "/sites/{site_id}/mapping/cleanup",
    summary="Clean up expired mapping sessions",
    tags=["Harris Matrix Mapping"]
)
async def v1_cleanup_expired_mappings(
    site_id: UUID,
    max_age_hours: int = Query(default=24, ge=1, le=168, description="Maximum age in hours before cleanup"),
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Clean up expired mapping sessions.
    
    This endpoint removes expired mappings from the database,
    helping to maintain system performance and storage efficiency.
    
    Args:
        site_id: UUID of the archaeological site
        max_age_hours: Maximum age in hours before cleanup (default: 24)
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Dictionary with cleanup results
        
    Raises:
        HTTPException: If site access is denied or cleanup fails
    """
    try:
        logger.info(f"Cleaning up expired mappings for site_id: {site_id}, max_age: {max_age_hours} hours")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access denied to this site",
                    "field": "site_id",
                    "value": str(site_id),
                    "suggestion": "Verify you have access to this site"
                }
            )
        
        # Initialize mapping service
        mapping_service = HarrisMatrixMappingService(db)
        
        # Perform cleanup
        cleaned_count = await mapping_service.cleanup_expired_sessions(max_age_hours)
        
        cleanup_result = {
            "site_id": str(site_id),
            "cleaned_count": cleaned_count,
            "max_age_hours": max_age_hours,
            "cleanup_time": logger._core.filter(lambda record: record["message"].startswith("Cleaned up")).current_timestamp if logger._core.filter else None,
            "success": True
        }
        
        logger.success(f"Cleanup completed for site {site_id}: {cleaned_count} mappings cleaned")
        return cleanup_result
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error during cleanup for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to cleanup expired mappings",
                "type": "cleanup_error",
                "details": str(e),
                "suggestion": "Please try again or contact support if the issue persists"
            }
        )


@router.get(
    "/sites/{site_id}/mapping/session/{session_id}/validate",
    summary="Validate the integrity of mappings in a session",
    tags=["Harris Matrix Mapping"]
)
async def v1_validate_session_integrity(
    site_id: UUID,
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Validate the integrity of mappings in a session.
    
    This endpoint performs comprehensive validation of mapping data,
    checking for structural issues and data consistency.
    
    Args:
        site_id: UUID of the archaeological site
        session_id: Session identifier
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Dictionary with validation results
        
    Raises:
        HTTPException: If site access is denied or validation fails
    """
    try:
        logger.info(f"Validating session integrity for site_id: {site_id}, session_id: {session_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access denied to this site",
                    "field": "site_id",
                    "value": str(site_id),
                    "suggestion": "Verify you have access to this site"
                }
            )
        
        # Initialize mapping service
        mapping_service = HarrisMatrixMappingService(db)
        
        # Perform validation
        validation_result = await mapping_service.validate_session_integrity(site_id, session_id)
        
        logger.success(f"Session validation completed for session {session_id}")
        return validation_result
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error validating session {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to validate session integrity",
                "type": "validation_error",
                "details": str(e),
                "suggestion": "Please check the session ID and try again"
            }
        )


@router.get(
    "/sites/{site_id}/mapping/sessions",
    summary="List all active mapping sessions for a site",
    tags=["Harris Matrix Mapping"]
)
async def v1_list_active_sessions(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    List all active mapping sessions for a site.
    
    This endpoint provides information about all currently active
    mapping sessions, useful for monitoring and debugging.
    
    Args:
        site_id: UUID of the archaeological site
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Dictionary with session information
        
    Raises:
        HTTPException: If site access is denied or listing fails
    """
    try:
        logger.info(f"Listing active sessions for site_id: {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Access denied to this site",
                    "field": "site_id",
                    "value": str(site_id),
                    "suggestion": "Verify you have access to this site"
                }
            )
        
        # Get site statistics which includes session information
        mapping_service = HarrisMatrixMappingService(db)
        stats = await mapping_service.get_site_mapping_statistics(site_id)
        
        # Return formatted session information
        sessions_info = {
            "site_id": str(site_id),
            "total_sessions": stats.get("total_sessions", 0),
            "total_users": stats.get("total_users", 0),
            "status_breakdown": stats.get("status_breakdown", {}),
            "earliest_session": stats.get("earliest_created"),
            "latest_session": stats.get("latest_created"),
            "success": True
        }
        
        logger.success(f"Active sessions listed for site {site_id}")
        return sessions_info
        
    except HTTPException:
        raise
        
    except Exception as e:
        logger.error(f"Error listing active sessions for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list active sessions",
                "type": "listing_error",
                "details": str(e),
                "suggestion": "Please try again or contact support if the issue persists"
            }
        )