# app/routes/api/v1/harris_matrix_atomic.py - Atomic Harris Matrix operations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from uuid import UUID
from typing import Dict, Any, Optional, List
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.services.harris_matrix_service import HarrisMatrixService
from app.models.harris_matrix_layout import HarrisMatrixLayout
from app.schemas.harris_matrix_editor import (
    HarrisMatrixAtomicSaveRequest,
    HarrisMatrixAtomicSaveResponse,
)
from app.exceptions import (
    HarrisMatrixValidationError,
    StratigraphicCycleDetected,
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    HarrisMatrixServiceError,
    BusinessLogicError
)

router = APIRouter()


async def verify_site_access(site_id: UUID, user_sites: list) -> bool:
    """Verify if user has access to the specified site"""
    return any(s["site_id"] == str(site_id) for s in user_sites)


@router.post(
    "/sites/{site_id}/atomic-save",
    summary="Atomically save Harris Matrix with units, relationships, and layout",
    tags=["Harris Matrix Atomic"]
)
async def v1_atomic_save_harris_matrix(
    site_id: UUID,
    request: HarrisMatrixAtomicSaveRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixAtomicSaveResponse:
    """
    Atomically save Harris Matrix with complete transaction consistency.
    
    This endpoint performs all Harris Matrix operations in a single atomic transaction:
    1. Create new units (bulk-create)
    2. Update existing units' relationships (bulk-update-sequenza-fisica)
    3. Save layout positions
    
    Either all operations succeed together, or the entire transaction is rolled back.
    This prevents partial database states and ensures data consistency.
    
    Args:
        site_id: UUID of the archaeological site
        request: Atomic save request containing all operations
        db: AsyncSession for database operations
        current_user_id: Current authenticated user ID
        user_sites: List of sites user has access to
        
    Returns:
        Comprehensive result with success/failure status for each operation
        
    Raises:
        HTTPException: With detailed error information if any operation fails
    """
    try:
        logger.info(f"Starting atomic Harris Matrix save for site_id: {site_id}")
        
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
        
        # Initialize service
        harris_service = HarrisMatrixService(db)
        
        # ATOMIC TRANSACTION: All operations must succeed or none
        async with db.begin() as transaction:
            try:
                logger.info("Starting atomic transaction for Harris Matrix save")
                
                # Track results for each operation
                operation_results = {
                    "new_units_created": 0,
                    "existing_units_updated": 0,
                    "layout_positions_saved": 0,
                    "relationships_processed": 0
                }
                unit_mapping = {}
                
                # STEP 1: Create new units (if any)
                if request.new_units and request.new_units.units:
                    logger.info(f"Creating {len(request.new_units.units)} new units")
                    
                    try:
                        # Convert Pydantic models to dictionaries with user context
                        units_data = []
                        for unit in request.new_units.units:
                            unit_dict = unit.dict(exclude_none=True)
                            unit_dict['created_by'] = str(current_user_id)
                            unit_dict['updated_by'] = str(current_user_id)
                            units_data.append(unit_dict)
                        
                        relationships_data = [rel.dict() for rel in request.new_units.relationships]
                        
                        # Perform bulk creation within the transaction
                        create_result = await harris_service.bulk_create_units_with_relationships(
                            site_id=site_id,
                            units_data=units_data,
                            relationships_data=relationships_data,
                            current_user_id=current_user_id
                        )
                        
                        operation_results["new_units_created"] = create_result['created_units']
                        operation_results["relationships_processed"] = create_result['created_relationships']
                        
                        # Store mapping for subsequent operations
                        unit_mapping = create_result.get('unit_mapping', {})
                        
                        logger.info(f"Successfully created {create_result['created_units']} new units")
                        
                    except Exception as e:
                        logger.error(f"Failed to create new units: {str(e)}")
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "error": "New units creation failed",
                                "type": "unit_creation_error",
                                "details": str(e),
                                "suggestion": "Check unit data and relationships",
                                "step": "new_units_creation"
                            }
                        )
                
                # STEP 2: Update existing units' relationships (if any)
                if request.existing_units_updates and request.existing_units_updates.updates:
                    logger.info(f"Updating relationships for {len(request.existing_units_updates.updates)} existing units")
                    
                    try:
                        # Perform bulk update within the transaction
                        update_result = await harris_service.bulk_update_sequenza_fisica_units(
                            site_id=site_id,
                            updates=request.existing_units_updates.updates
                        )
                        
                        operation_results["existing_units_updated"] = update_result.get('updated_count', 0)
                        
                        logger.info(f"Successfully updated relationships for {operation_results['existing_units_updated']} existing units")
                        
                    except Exception as e:
                        logger.error(f"Failed to update existing units: {str(e)}")
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "error": "Existing units update failed",
                                "type": "units_update_error",
                                "details": str(e),
                                "suggestion": "Check relationship data and unit IDs",
                                "step": "existing_units_update"
                            }
                        )
                
                # STEP 3: Save layout positions (if any)
                if request.layout_positions and request.layout_positions.positions:
                    logger.info(f"Saving {len(request.layout_positions.positions)} layout positions")
                    
                    try:
                        # Delete existing layout positions for this site
                        await db.execute(
                            delete(HarrisMatrixLayout).where(
                                HarrisMatrixLayout.site_id == str(site_id)
                            )
                        )
                        
                        # Insert new positions
                        for pos in request.layout_positions.positions:
                            layout = HarrisMatrixLayout(
                                site_id=str(site_id),
                                unit_id=pos.unit_id,
                                unit_type=pos.unit_type,
                                x=pos.x,
                                y=pos.y
                            )
                            db.add(layout)
                        
                        await db.flush()  # Ensure layout data is written
                        operation_results["layout_positions_saved"] = len(request.layout_positions.positions)
                        
                        logger.info(f"Successfully saved {operation_results['layout_positions_saved']} layout positions")
                        
                    except Exception as e:
                        logger.error(f"Failed to save layout positions: {str(e)}")
                        raise HTTPException(
                            status_code=500,
                            detail={
                                "error": "Layout positions save failed",
                                "type": "layout_save_error",
                                "details": str(e),
                                "suggestion": "Check layout position data",
                                "step": "layout_save"
                            }
                        )
                
                # All operations completed successfully - transaction will commit automatically
                logger.info("Atomic transaction completed successfully")
                
                # Build comprehensive response
                response = HarrisMatrixAtomicSaveResponse(
                    success=True,
                    message=f"Atomic save completed successfully: {operation_results['new_units_created']} new units, {operation_results['existing_units_updated']} updated units, {operation_results['layout_positions_saved']} layout positions",
                    site_id=site_id,
                    operation_results=operation_results,
                    unit_mapping=unit_mapping,
                    validation_performed=True,
                    transaction_rolled_back=False
                )
                
                logger.info(f"Atomic Harris Matrix save completed successfully for site {site_id}: {operation_results}")
                return response
                
            except HTTPException:
                # HTTPException should be re-raised for proper error responses
                # The transaction will be rolled back automatically due to the exception
                raise
                
            except Exception as e:
                # Any other exception will cause automatic transaction rollback
                logger.error(f"Unexpected error in atomic transaction: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "Unexpected error during atomic save",
                        "type": "internal_error",
                        "details": str(e),
                        "transaction_rolled_back": True,
                        "suggestion": "Please try again or contact support if the issue persists"
                    }
                )
    
    except HTTPException:
        # Re-raise HTTP exceptions (including our enhanced ones)
        raise
    
    except Exception as e:
        logger.error(f"Error in atomic Harris Matrix save for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error during atomic save",
                "type": "system_error", 
                "details": str(e),
                "suggestion": "Please try again or contact support if the issue persists"
            }
        )


@router.get(
    "/sites/{site_id}/atomic-save/health",
    summary="Health check for atomic save operations",
    tags=["Harris Matrix Atomic"]
)
async def v1_atomic_save_health_check(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Health check for atomic save operations.
    
    This endpoint checks if the atomic save functionality is working properly
    by testing database connectivity and basic transaction capabilities.
    """
    try:
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Test database connection with a simple transaction
        async with db.begin() as test_transaction:
            # Simple test query to verify database is accessible
            result = await db.execute("SELECT 1 as test_value")
            test_row = result.fetchone()
            
            if not test_row or test_row.test_value != 1:
                raise Exception("Database test query failed")
        
        return {
            "status": "healthy",
            "site_id": str(site_id),
            "database_connection": "ok",
            "transaction_support": "ok",
            "message": "Atomic save functionality is ready"
        }
        
    except Exception as e:
        logger.error(f"Atomic save health check failed for site {site_id}: {str(e)}")
        return {
            "status": "unhealthy",
            "site_id": str(site_id),
            "database_connection": "error",
            "transaction_support": "unknown",
            "error": str(e),
            "message": "Atomic save functionality is not available"
        }