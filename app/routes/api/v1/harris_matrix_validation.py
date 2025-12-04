# app/routes/api/v1/harris_matrix_validation.py
"""
API Routes for Harris Matrix Reference Validation and Cleanup

This module provides REST API endpoints for validating and cleaning up broken
references in the Harris Matrix system. It integrates with both the enhanced unit
resolver service and the centralized stratigraphy utilities from
app.utils.stratigraphy_helpers to provide comprehensive reference management.

The module now includes enhanced validation capabilities using centralized utilities:
- Cycle detection with CycleDetector
- Business rules validation with StratigraphicRulesValidator
- Comprehensive validation with validate_stratigraphic_data()
- Enhanced error handling with specialized exception classes

Endpoints:
- GET /api/v1/harris-matrix/validation/sites/{site_id} - Validate specific site
- GET /api/v1/harris-matrix/validation/sites - Validate all sites
- POST /api/v1/harris-matrix/validation/cleanup/{site_id} - Cleanup broken references
- GET /api/v1/harris-matrix/validation/statistics/{site_id} - Reference statistics
- POST /api/v1/harris-matrix/validation/backup/{site_id} - Create backup
- POST /api/v1/harris-matrix/validation/restore/{site_id} - Restore from backup
- GET /api/v1/harris-matrix/validation/comprehensive/{site_id} - Comprehensive validation
- POST /api/v1/harris-matrix/validation/validate-business-rules/{site_id} - Business rules validation
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from loguru import logger

from app.database.db import get_async_db
from app.services.harris_matrix_unit_resolver import UnitResolver
from app.utils.stratigraphy_helpers import (
    CycleDetector,
    StratigraphicRulesValidator,
    validate_stratigraphic_data,
    create_rules_validator,
    parse_target_reference,
    get_default_sequenza_fisica
)
from app.exceptions import (
    HarrisMatrixValidationError,
    StratigraphicCycleDetected,
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    HarrisMatrixServiceError
)
from app.core.security import get_current_user
from app.models.users import User


# Create router
router = APIRouter(
    prefix="/harris-matrix/validation",
    tags=["harris-matrix-validation"]
)


# Pydantic Models
class ValidationError(BaseModel):
    """Model for validation errors."""
    error: str
    unit_code: str
    unit_type: str
    reference_type: Optional[str] = None
    target_code: Optional[str] = None


class ValidationResult(BaseModel):
    """Model for validation results."""
    site_id: str
    validation_time: str
    broken_references: Dict[str, List[str]]
    total_issues: int
    us_units_with_issues: int
    usm_units_with_issues: int
    health_score: float
    severity: str
    recommendations: List[str]


class CleanupRequest(BaseModel):
    """Model for cleanup requests."""
    create_backup: bool = Field(default=True, description="Create backup before cleanup")
    dry_run: bool = Field(default=False, description="Preview cleanup without applying changes")


class CleanupResult(BaseModel):
    """Model for cleanup results."""
    site_id: str
    cleanup_time: str
    backup_created: bool
    backup_info: Optional[Dict[str, Any]]
    cleanup_statistics: Dict[str, int]
    post_cleanup_statistics: Dict[str, Any]
    success: bool


class BatchValidationRequest(BaseModel):
    """Model for batch validation requests."""
    site_ids: Optional[List[str]] = Field(default=None, description="Specific site IDs to validate")
    parallel_workers: int = Field(default=4, ge=1, le=10, description="Number of parallel workers")
    include_details: bool = Field(default=True, description="Include detailed analysis")


class BatchValidationResult(BaseModel):
    """Model for batch validation results."""
    validation_time: str
    total_sites: int
    sites_validated: int
    sites_with_issues: int
    sites_without_issues: int
    total_issues: int
    average_health_score: float
    overall_severity: str
    site_summaries: Dict[str, Dict[str, Any]]
    recommendations: List[str]


class StatisticsResult(BaseModel):
    """Model for statistics results."""
    site_id: str
    timestamp: str
    us_units: Dict[str, Any]
    usm_units: Dict[str, Any]
    overall: Dict[str, Any]


class BackupResult(BaseModel):
    """Model for backup/restore results."""
    site_id: str
    operation: str
    timestamp: str
    success: bool
    backup_id: Optional[str]
    unit_counts: Dict[str, int]
    error: Optional[str] = None


class ComprehensiveValidationResult(BaseModel):
    """Model for comprehensive validation results using centralized utilities."""
    site_id: str
    validation_timestamp: str
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    business_rules: Dict[str, Any]
    statistics: Dict[str, Any]


# Utility Functions
async def get_unit_resolver(db: AsyncSession) -> UnitResolver:
    """Get unit resolver instance."""
    return UnitResolver(db)


# API Endpoints

@router.get("/sites/{site_id}", response_model=ValidationResult)
async def validate_site_references(
    site_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    include_details: bool = Query(default=True, description="Include detailed analysis")
):
    """
    Validate references for a specific archaeological site.
    
    This endpoint analyzes all US and USM units in the specified site,
    identifying broken references and providing actionable recommendations
    for fixing data integrity issues.
    
    Args:
        site_id: UUID of the archaeological site
        include_details: Whether to include detailed analysis
        
    Returns:
        ValidationResult with comprehensive validation information
    """
    try:
        logger.info(f"User {current_user.id} validating references for site {site_id}")
        
        resolver = await get_unit_resolver(db)
        
        # Perform validation
        broken_refs = await resolver.validate_references(site_id)
        
        # Get statistics
        stats = await resolver.get_reference_statistics(site_id)
        
        # Create backup before validation
        backup_info = await resolver.create_reference_backup(site_id)
        
        # Calculate summary metrics
        total_issues = sum(len(issues) for issues in broken_refs.values())
        
        # Assess severity
        health_score = stats.get('overall', {}).get('health_score', 0.0)
        if health_score >= 95:
            severity = 'minimal'
        elif health_score >= 85:
            severity = 'low'
        elif health_score >= 70:
            severity = 'moderate'
        elif health_score >= 50:
            severity = 'high'
        else:
            severity = 'critical'
        
        # Generate recommendations
        recommendations = await _generate_recommendations(broken_refs, stats)
        
        result = ValidationResult(
            site_id=site_id,
            validation_time=datetime.now().isoformat(),
            broken_references=broken_refs,
            total_issues=total_issues,
            us_units_with_issues=len(broken_refs.get('us_units', [])),
            usm_units_with_issues=len(broken_refs.get('usm_units', [])),
            health_score=health_score,
            severity=severity,
            recommendations=recommendations
        )
        
        logger.info(f"Validation completed for site {site_id}: {total_issues} issues found")
        return result
        
    except Exception as e:
        logger.error(f"Error validating site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Validation error: {str(e)}"
        )


@router.get("/sites", response_model=BatchValidationResult)
async def validate_all_sites(
    request: BatchValidationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Validate references across all archaeological sites.
    
    This endpoint performs batch validation across multiple sites,
    providing a comprehensive overview of reference integrity across
    the entire system.
    
    Args:
        request: Batch validation parameters
        
    Returns:
        BatchValidationResult with comprehensive batch information
    """
    try:
        logger.info(f"User {current_user.id} starting batch validation")
        
        resolver = await get_unit_resolver(db)
        
        # Determine which sites to validate
        if request.site_ids:
            site_ids = request.site_ids
        else:
            # Get all site IDs from database
            sites_query = "SELECT id FROM archaeological_sites WHERE deleted_at IS NULL"
            sites_result = await db.execute(sites_query)
            site_ids = [str(row[0]) for row in sites_result.fetchall()]
        
        if not site_ids:
            raise HTTPException(
                status_code=404,
                detail="No sites found for validation"
            )
        
        # Perform batch validation
        batch_results = await resolver.batch_validate_references(
            site_ids, request.parallel_workers
        )
        
        # Compile comprehensive report
        total_sites = len(site_ids)
        sites_with_issues = 0
        total_issues = 0
        health_scores = []
        
        site_summaries = {}
        
        for site_id in site_ids:
            if site_id in batch_results:
                site_result = batch_results[site_id]
                
                if 'error' not in site_result:
                    site_issues = sum(len(issues) for issues in site_result.values())
                    total_issues += site_issues
                    
                    if site_issues > 0:
                        sites_with_issues += 1
                    
                    # Calculate health score
                    health_score = 100.0 - (site_issues * 5)  # Simple calculation
                    health_score = max(0.0, min(100.0, health_score))
                    health_scores.append(health_score)
                    
                    site_summaries[site_id] = {
                        'issues': site_issues,
                        'health_score': health_score,
                        'severity': _assess_severity(site_issues, {'overall': {'health_score': health_score}})
                    }
        
        avg_health_score = sum(health_scores) / len(health_scores) if health_scores else 100.0
        
        # Generate batch recommendations
        recommendations = _generate_batch_recommendations(total_sites, sites_with_issues, total_issues)
        
        result = BatchValidationResult(
            validation_time=datetime.now().isoformat(),
            total_sites=total_sites,
            sites_validated=len(batch_results),
            sites_with_issues=sites_with_issues,
            sites_without_issues=total_sites - sites_with_issues,
            total_issues=total_issues,
            average_health_score=round(avg_health_score, 2),
            overall_severity=_assess_severity(total_issues, {'overall': {'health_score': avg_health_score}}),
            site_summaries=site_summaries,
            recommendations=recommendations
        )
        
        logger.info(f"Batch validation completed: {sites_with_issues}/{total_sites} sites have issues")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch validation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Batch validation error: {str(e)}"
        )


@router.post("/cleanup/{site_id}", response_model=CleanupResult)
async def cleanup_site_references(
    site_id: str,
    request: CleanupRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Clean up broken references for a specific site.
    
    This endpoint removes orphaned references from US and USM units,
    improving data integrity and preventing potential system errors.
    A backup is automatically created before cleanup unless explicitly disabled.
    
    Args:
        site_id: UUID of the archaeological site
        request: Cleanup parameters
        
    Returns:
        CleanupResult with cleanup statistics
    """
    try:
        logger.info(f"User {current_user.id} cleaning up references for site {site_id}")
        
        resolver = await get_unit_resolver(db)
        
        # Create backup if requested
        backup_info = None
        if request.create_backup and not request.dry_run:
            backup_info = await resolver.create_reference_backup(site_id)
            logger.info(f"Backup created: {backup_info['backup_id']}")
        
        if request.dry_run:
            # Preview cleanup without making changes
            broken_refs = await resolver.validate_references(site_id)
            total_issues = sum(len(issues) for issues in broken_refs.values())
            
            # Simulate cleanup statistics
            cleanup_stats = {
                'us_units_cleaned': len(broken_refs.get('us_units', [])),
                'usm_units_cleaned': len(broken_refs.get('usm_units', [])),
                'references_removed': total_issues,
                'errors': 0
            }
            
            # Get current statistics
            post_cleanup_stats = await resolver.get_reference_statistics(site_id)
            
            logger.info(f"Dry run completed for site {site_id}: {total_issues} references would be removed")
            
        else:
            # Perform actual cleanup
            cleanup_stats = await resolver.cleanup_broken_references(site_id)
            
            # Get post-cleanup statistics
            post_cleanup_stats = await resolver.get_reference_statistics(site_id)
            
            logger.info(f"Cleanup completed for site {site_id}: {cleanup_stats['references_removed']} references removed")
        
        result = CleanupResult(
            site_id=site_id,
            cleanup_time=datetime.now().isoformat(),
            backup_created=request.create_backup and not request.dry_run,
            backup_info=backup_info,
            cleanup_statistics=cleanup_stats,
            post_cleanup_statistics=post_cleanup_stats,
            success=cleanup_stats['errors'] == 0
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error cleaning up site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup error: {str(e)}"
        )


@router.get("/statistics/{site_id}", response_model=StatisticsResult)
async def get_site_statistics(
    site_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive reference statistics for a site.
    
    This endpoint provides detailed statistics about reference usage,
    health scores, and data integrity metrics for the specified site.
    
    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        StatisticsResult with comprehensive site statistics
    """
    try:
        logger.info(f"User {current_user.id} getting statistics for site {site_id}")
        
        resolver = await get_unit_resolver(db)
        stats = await resolver.get_reference_statistics(site_id)
        
        result = StatisticsResult(
            site_id=site_id,
            timestamp=stats.get('timestamp', datetime.now().isoformat()),
            us_units=stats.get('us_units', {}),
            usm_units=stats.get('usm_units', {}),
            overall=stats.get('overall', {})
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting statistics for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Statistics error: {str(e)}"
        )


@router.post("/backup/{site_id}", response_model=BackupResult)
async def create_site_backup(
    site_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a backup of all unit references for a site.
    
    This endpoint creates a comprehensive backup of the current
    reference state, enabling rollback capabilities for cleanup operations.
    
    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        BackupResult with backup information
    """
    try:
        logger.info(f"User {current_user.id} creating backup for site {site_id}")
        
        resolver = await get_unit_resolver(db)
        backup_info = await resolver.create_reference_backup(site_id)
        
        result = BackupResult(
            site_id=site_id,
            operation="backup",
            timestamp=datetime.now().isoformat(),
            success=backup_info['backup_id'] is not None,
            backup_id=backup_info['backup_id'],
            unit_counts={
                'us_units': backup_info['us_unit_count'],
                'usm_units': backup_info['usm_unit_count']
            },
            error=None
        )
        
        logger.info(f"Backup created for site {site_id}: {backup_info['backup_id']}")
        return result
        
    except Exception as e:
        logger.error(f"Error creating backup for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Backup error: {str(e)}"
        )


@router.post("/restore/{site_id}", response_model=BackupResult)
async def restore_site_backup(
    site_id: str,
    backup_data: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Restore references from a backup for a site.
    
    This endpoint restores unit references from a previously created backup,
    enabling rollback capabilities for cleanup operations.
    
    Args:
        site_id: UUID of the archaeological site
        backup_data: Backup data structure from previous backup operation
        
    Returns:
        BackupResult with restore information
    """
    try:
        logger.info(f"User {current_user.id} restoring backup for site {site_id}")
        
        resolver = await get_unit_resolver(db)
        restore_stats = await resolver.restore_reference_backup(site_id, backup_data)
        
        # Calculate unit counts from restore stats
        unit_counts = {
            'us_units': restore_stats['us_units_restored'],
            'usm_units': restore_stats['usm_units_restored']
        }
        
        result = BackupResult(
            site_id=site_id,
            operation="restore",
            timestamp=datetime.now().isoformat(),
            success=restore_stats['errors'] == 0,
            backup_id=None,  # Not applicable for restore
            unit_counts=unit_counts,
            error=None if restore_stats['errors'] == 0 else f"{restore_stats['errors']} errors occurred"
        )
        
        logger.info(f"Backup restored for site {site_id}: {restore_stats['references_restored']} references restored")
        return result
        
    except Exception as e:
        logger.error(f"Error restoring backup for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Restore error: {str(e)}"
        )


@router.get("/health/{site_id}")
async def get_site_health_check(
    site_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a quick health check for a site's reference integrity.
    
    This endpoint provides a lightweight health assessment without
    performing full validation, suitable for monitoring dashboards.
    
    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        Simple health check result
    """
    try:
        resolver = await get_unit_resolver(db)
        
        # Get basic statistics (lighter than full validation)
        stats = await resolver.get_reference_statistics(site_id)
        
        health_score = stats.get('overall', {}).get('health_score', 0.0)
        
        if health_score >= 95:
            status = "healthy"
            message = "Reference integrity is excellent"
        elif health_score >= 85:
            status = "good"
            message = "Reference integrity is good with minor issues"
        elif health_score >= 70:
            status = "warning"
            message = "Reference integrity requires attention"
        else:
            status = "critical"
            message = "Reference integrity requires immediate attention"
        
        return {
            "site_id": site_id,
            "health_score": health_score,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "total_units": stats.get('overall', {}).get('total_units', 0),
            "total_references": stats.get('overall', {}).get('total_references', 0),
            "broken_references": stats.get('overall', {}).get('total_broken_refs', 0)
        }
        
    except Exception as e:
        logger.error(f"Error in health check for site {site_id}: {str(e)}")
        return {
            "site_id": site_id,
            "health_score": 0.0,
            "status": "error",
            "message": f"Health check failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/comprehensive/{site_id}", response_model=ComprehensiveValidationResult)
async def validate_site_comprehensive(
    site_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Perform comprehensive validation using centralized stratigraphy utilities.
    
    This endpoint uses the enhanced validation capabilities from stratigraphy_helpers
    to provide deeper analysis including business rules validation, cycle detection,
    and comprehensive data integrity checks.
    
    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        ComprehensiveValidationResult with detailed validation information
    """
    try:
        logger.info(f"User {current_user.id} performing comprehensive validation for site {site_id}")
        
        # Convert site_id to UUID
        site_uuid = UUID(site_id)
        
        # Use the comprehensive validation function
        validation_result = await validate_stratigraphic_data(db, site_uuid)
        
        # Format result
        result = ComprehensiveValidationResult(
            site_id=site_id,
            validation_timestamp=validation_result.get('validation_timestamp', datetime.now().isoformat()),
            is_valid=validation_result['is_valid'],
            errors=validation_result['errors'],
            warnings=validation_result['warnings'],
            business_rules=validation_result['business_rules'],
            statistics=validation_result['statistics']
        )
        
        logger.info(f"Comprehensive validation completed for site {site_id}: {'PASS' if validation_result['is_valid'] else 'FAIL'}")
        return result
        
    except (HarrisMatrixValidationError, StratigraphicCycleDetected,
            InvalidStratigraphicRelation, UnitCodeConflict) as e:
        # Handle specific stratigraphy validation errors
        logger.error(f"Stratigraphy validation error for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Validation failed: {str(e)}"
        )
    except HarrisMatrixServiceError as e:
        # Handle service-level errors
        logger.error(f"Harris Matrix service error for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Service unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in comprehensive validation for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Comprehensive validation error: {str(e)}"
        )


@router.post("/validate-business-rules/{site_id}")
async def validate_business_rules(
    site_id: str,
    units_data: Optional[List[Dict[str, Any]]] = None,
    relationships_data: Optional[List[Dict[str, Any]]] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Validate business rules for stratigraphic relationships.
    
    This endpoint uses the centralized StratigraphicRulesValidator to ensure
    that all relationships follow archaeological principles and domain constraints.
    
    Args:
        site_id: UUID of the archaeological site
        units_data: Optional list of units to validate (if not provided, uses existing units)
        relationships_data: Optional list of relationships to validate
        
    Returns:
        Business rules validation result
    """
    try:
        logger.info(f"User {current_user.id} validating business rules for site {site_id}")
        
        # Convert site_id to UUID
        site_uuid = UUID(site_id)
        
        # Use the comprehensive validation which includes business rules
        validation_result = await validate_stratigraphic_data(db, site_uuid, units_data, relationships_data)
        
        return {
            "site_id": site_id,
            "validation_timestamp": validation_result.get('validation_timestamp', datetime.now().isoformat()),
            "business_rules_passed": validation_result['is_valid'],
            "business_rule_violations": validation_result['business_rules'],
            "errors": validation_result['errors'],
            "warnings": validation_result['warnings']
        }
        
    except (InvalidStratigraphicRelation, UnitCodeConflict) as e:
        # Handle specific business rule violations
        logger.error(f"Business rules violation for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Business rules validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error validating business rules for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Business rules validation error: {str(e)}"
        )


# Helper Functions

async def _generate_recommendations(broken_refs: Dict[str, List[str]], stats: Dict[str, Any]) -> List[str]:
    """Generate actionable recommendations based on validation results."""
    recommendations = []
    
    total_issues = sum(len(issues) for issues in broken_refs.values())
    
    if total_issues == 0:
        recommendations.append("✅ No broken references found. System is healthy.")
        return recommendations
    
    # General recommendations
    if total_issues > 0:
        recommendations.append("🔧 Run automated cleanup to remove orphaned references")
    
    # Specific recommendations based on issue types
    if len(broken_refs.get('us_units', [])) > 0:
        recommendations.append("📝 Review US units with broken references for potential data entry errors")
    
    if len(broken_refs.get('usm_units', [])) > 0:
        recommendations.append("🧱 Review USM units with broken references for structural relationship errors")
    
    if len(broken_refs.get('cross_type_issues', [])) > 0:
        recommendations.append("⚠️ Address cross-type reference inconsistencies (US ↔ USM)")
    
    if len(broken_refs.get('numeric_format_issues', [])) > 0:
        recommendations.append("🔢 Standardize numeric formats in unit codes and references")
    
    # Health-based recommendations
    health_score = stats.get('overall', {}).get('health_score', 100.0)
    if health_score < 80:
        recommendations.append("⚠️ Low health score detected. Consider comprehensive data audit")
    
    if health_score < 60:
        recommendations.append("🚨 Critical health score. Immediate attention required")
    
    # Preventive recommendations
    recommendations.append("🛡️ Implement validation rules to prevent future broken references")
    recommendations.append("📊 Set up regular reference integrity monitoring")
    
    return recommendations


def _assess_severity(total_issues: int, stats: Dict[str, Any]) -> str:
    """Assess the severity of reference issues."""
    health_score = stats.get('overall', {}).get('health_score', 100.0)
    
    if health_score >= 95:
        return 'minimal'
    elif health_score >= 85:
        return 'low'
    elif health_score >= 70:
        return 'moderate'
    elif health_score >= 50:
        return 'high'
    else:
        return 'critical'


def _generate_batch_recommendations(total_sites: int, sites_with_issues: int, total_issues: int) -> List[str]:
    """Generate recommendations for batch validation results."""
    recommendations = []
    
    if sites_with_issues == 0:
        recommendations.append("✅ All sites have healthy reference integrity")
        return recommendations
    
    issue_percentage = (sites_with_issues / total_sites) * 100
    
    if issue_percentage > 50:
        recommendations.append("🚨 More than 50% of sites have reference issues. Consider system-wide data audit")
    elif issue_percentage > 25:
        recommendations.append("⚠️ Significant number of sites have issues. Plan systematic cleanup")
    else:
        recommendations.append("🔧 Targeted cleanup recommended for affected sites")
    
    if total_issues > 100:
        recommendations.append("📊 High volume of broken references. Automated cleanup recommended")
    
    recommendations.append("🛡️ Implement validation rules to prevent future reference issues")
    recommendations.append("📈 Set up regular monitoring of reference integrity")
    
    return recommendations