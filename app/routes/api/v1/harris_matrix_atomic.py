# app/routes/api/v1/harris_matrix_atomic.py - Atomic Harris Matrix operations

from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from uuid import UUID
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.services.harris_matrix_service import HarrisMatrixService
from app.services.harris_matrix_id_normalizer import UnitIDNormalizer, create_unit_id_normalizer
from app.services.harris_matrix_mapping_service import HarrisMatrixMappingService
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
    user_sites: list = Depends(get_current_user_sites_with_blacklist),
    x_session_id: Optional[str] = Header(None, description="Session identifier for mapping tracking")
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
        
        # Generate or extract session ID
        session_id = x_session_id or f"atomic-save-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(current_user_id)[:8]}"
        
        # Initialize services
        harris_service = HarrisMatrixService(db)
        id_normalizer = create_unit_id_normalizer(db)
        mapping_service = HarrisMatrixMappingService(db)
        
        # Create mapping session
        transaction_id = await mapping_service.create_mapping_session(
            site_id=site_id,
            session_id=session_id,
            user_id=current_user_id
        )
        
        logger.info(f"Created mapping session: {transaction_id} for session: {session_id}")
        
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
                
                # Initialize persistent unit mapping
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
                        
                        # Get in-memory mapping from service result
                        temp_unit_mapping = create_result.get('unit_mapping', {})
                        
                        # Persist all mappings to database
                        for temp_id, db_id_str in temp_unit_mapping.items():
                            # Find the corresponding unit data to get the unit code
                            unit_data = next((u for u in units_data if u.get('temp_id') == temp_id), None)
                            if unit_data:
                                unit_code = unit_data.get('code', 'UNKNOWN')
                                db_id = UUID(db_id_str)
                                
                                # Save persistent mapping
                                await mapping_service.save_temp_to_db_mapping(
                                    site_id=site_id,
                                    session_id=session_id,
                                    temp_id=temp_id,
                                    db_id=db_id,
                                    unit_code=unit_code,
                                    user_id=current_user_id
                                )
                        
                        # Store mapping for subsequent operations
                        unit_mapping = temp_unit_mapping
                        
                        logger.info(f"Persisted {len(temp_unit_mapping)} unit mappings to database")
                        
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
                if request.existing_units_updates:
                    logger.info(f"Updating relationships for existing units")
                    logger.debug(f"DEBUG: existing_units_updates structure: {request.existing_units_updates}")
                    
                    try:
                        # Handle both schema formats: direct dict or with .updates wrapper
                        updates_dict = {}
                        if hasattr(request.existing_units_updates, 'updates'):
                            # Schema format: {updates: {unit_id: {sequenza_fisica: {...}}}}
                            for unit_id, update_data in request.existing_units_updates.updates.items():
                                updates_dict[unit_id] = update_data
                            logger.info(f"Processing {len(updates_dict)} updates from schema format")
                        else:
                            # Direct format: {unit_id: {sequenza_fisica: {...}}}
                            for unit_id, update_data in request.existing_units_updates.items():
                                updates_dict[unit_id] = update_data
                            logger.info(f"Processing {len(updates_dict)} updates from direct format")
                        
                        logger.debug(f"DEBUG: Final updates for bulk_update_sequenza_fisica_units: {updates_dict}")
                        
                        # Perform bulk update within the transaction
                        update_result = await harris_service.bulk_update_sequenza_fisica_units(
                            site_id=site_id,
                            updates=updates_dict
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
                layout_positions = None
                
                # Handle both layout_save and layout_positions field names
                if hasattr(request, 'layout_save') and request.layout_save and request.layout_save.positions:
                    layout_positions = request.layout_save
                    logger.info(f"Saving {len(layout_positions.positions)} layout positions from layout_save")
                elif hasattr(request, 'layout_positions') and request.layout_positions and request.layout_positions.positions:
                    layout_positions = request.layout_positions
                    logger.info(f"Saving {len(layout_positions.positions)} layout positions from layout_positions")
                
                if layout_positions:
                    logger.debug(f"DEBUG: layout structure: {layout_positions}")
                    
                    try:
                        # Delete existing layout positions for this site
                        await db.execute(
                            delete(HarrisMatrixLayout).where(
                                HarrisMatrixLayout.site_id == str(site_id)
                            )
                        )
                        
                        # Insert new positions with ID normalization
                        normalized_positions_count = 0
                        for pos in layout_positions.positions:
                            # Normalize the unit ID using the new normalizer
                            normalized_unit_id = await id_normalizer.normalize_for_layout_lookup(
                                pos.unit_id, pos.unit_type, db
                            )
                            
                            if normalized_unit_id:
                                layout = HarrisMatrixLayout(
                                    site_id=str(site_id),
                                    unit_id=normalized_unit_id,  # Use normalized ID
                                    unit_type=pos.unit_type,
                                    x=pos.x,
                                    y=pos.y
                                )
                                db.add(layout)
                                normalized_positions_count += 1
                            else:
                                logger.warning(f"Could not normalize unit ID: {pos.unit_id} (type: {pos.unit_type}) - skipping layout save")
                        
                        await db.flush()  # Ensure layout data is written
                        operation_results["layout_positions_saved"] = normalized_positions_count
                        
                        if normalized_positions_count != len(layout_positions.positions):
                            logger.warning(f"Only {normalized_positions_count}/{len(layout_positions.positions)} layout positions normalized and saved")
                        
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
                
                # Commit all mappings for the successful transaction
                commit_result = await mapping_service.commit_mappings(
                    site_id=site_id,
                    session_id=session_id,
                    transaction_id=transaction_id
                )
                
                logger.info(f"Committed {commit_result['committed_count']} mappings")
                
                # All operations completed successfully - transaction will commit automatically
                logger.info("Atomic transaction completed successfully")
                
                # Build comprehensive response with mapping metadata
                response = HarrisMatrixAtomicSaveResponse(
                    success=True,
                    message=f"Atomic save completed successfully: {operation_results['new_units_created']} new units, {operation_results['existing_units_updated']} updated units, {operation_results['layout_positions_saved']} layout positions",
                    site_id=site_id,
                    operation_results=operation_results,
                    unit_mapping=unit_mapping,
                    validation_performed=True,
                    transaction_rolled_back=False,
                    # NEW: Metadata for recovery
                    session_id=session_id,
                    transaction_id=transaction_id,
                    created_units_count=operation_results["new_units_created"],
                    checkpoint_time=datetime.utcnow(),
                    mapping_status="committed"
                )
                
                logger.info(f"Atomic Harris Matrix save completed successfully for site {site_id}: {operation_results}")
                return response
                
            except HTTPException:
                # HTTPException should be re-raised for proper error responses
                # Rollback mappings before re-raising
                try:
                    await mapping_service.rollback_mappings(site_id=site_id, session_id=session_id)
                    logger.info(f"Rolled back mappings for session {session_id} due to HTTPException")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback mappings: {str(rollback_error)}")
                # The transaction will be rolled back automatically due to the exception
                raise
                
            except Exception as e:
                # Any other exception will cause automatic transaction rollback
                logger.error(f"Unexpected error in atomic transaction: {str(e)}", exc_info=True)
                
                # Rollback mappings on failure
                try:
                    rollback_result = await mapping_service.rollback_mappings(site_id=site_id, session_id=session_id)
                    logger.info(f"Rolled back {rollback_result['rolled_back_count']} mappings for session {session_id}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback mappings: {str(rollback_error)}")
                
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "Unexpected error during atomic save",
                        "type": "internal_error",
                        "details": str(e),
                        "transaction_rolled_back": True,
                        "session_id": session_id,
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