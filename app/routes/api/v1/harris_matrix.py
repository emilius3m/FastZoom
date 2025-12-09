# app/routes/api/v1/harris_matrix.py - Harris Matrix API v1 endpoints

from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from uuid import UUID
from typing import Dict, Any, Optional, List
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.services.harris_matrix_service import HarrisMatrixService
from app.services.harris_matrix_mapping_service import HarrisMatrixMappingService
from app.services.harris_matrix_validation_service import HarrisMatrixValidationService
from app.models.harris_matrix_layout import HarrisMatrixLayout
from app.schemas.harris_matrix_editor import (
    HarrisMatrixBulkCreateRequest,
    HarrisMatrixBulkCreateResponse,
    HarrisMatrixBulkUpdateRequest,
    HarrisMatrixBulkUpdateResponse,
    HarrisMatrixDeleteRequest,
    HarrisMatrixDeleteResponse,
    HarrisMatrixValidationResult,
    HarrisMatrixGraphData,
    HarrisMatrixNode,
    HarrisMatrixEdge,
    StratigraphicRelation,
    UnitTypeEnum,
    TipoUSEnum,
    RelationshipValidation,
    CycleDetectionResult,
    UnitCodeValidation,
    HarrisMatrixBulkCreateUnit,
    HarrisMatrixBulkCreateRelationship,
    HarrisMatrixLayoutSaveRequest,
    NodePosition,
    SequenzaFisicaBulkUpdateRequest,
    HarrisMatrixAtomicSaveRequest,
    HarrisMatrixAtomicSaveResponse
)
from app.exceptions import (
    HarrisMatrixValidationError,
    StratigraphicCycleDetected,
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    HarrisMatrixServiceError,
    BusinessLogicError
)
from app.exceptions.harris_matrix import StaleReferenceError
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from sqlalchemy import select, and_, or_, delete
from app.utils.stratigraphy_helpers import (
    UnitLookupService,
    CycleDetector,
    StratigraphicRulesValidator
)

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
        
        # Use centralized unit lookup service
        unit_lookup = UnitLookupService(db)
        unit = await unit_lookup.get_unit_by_code(site_id, unit_code, unit_type)
        
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


# ===== HELPER FUNCTIONS FOR ENHANCED VALIDATION =====

async def _validate_bulk_create_request(
    request: HarrisMatrixBulkCreateRequest,
    site_id: UUID,
    unit_resolver,
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Comprehensive validation for bulk create requests.
    
    Args:
        request: Bulk create request to validate
        site_id: Site ID for context
        unit_resolver: Unit resolver instance
        db: Database session for validation
        
    Returns:
        Dictionary with validation results, errors, warnings, and suggestions
    """
    errors = []
    warnings = []
    field_errors = {}
    suggestions = []
    
    try:
        logger.info(f"Starting comprehensive validation for {len(request.units)} units")
        
        # 1. Basic structure validation
        if not request.units:
            errors.append("At least one unit must be provided")
            field_errors["units"] = "Required field missing or empty"
            suggestions.append("Add at least one unit to create")
        
        if len(request.units) > 100:
            warnings.append(f"Large request with {len(request.units)} units may impact performance")
            suggestions.append("Consider breaking this into smaller requests")
        
        # 2. Unit validation
        unit_validation = await _validate_units(
            request.units, site_id, unit_resolver, db
        )
        errors.extend(unit_validation["errors"])
        warnings.extend(unit_validation["warnings"])
        field_errors.update(unit_validation["field_errors"])
        suggestions.extend(unit_validation["suggestions"])
        
        # 3. Relationship validation
        relationship_validation = await _validate_relationships(
            request.units, request.relationships, unit_resolver
        )
        errors.extend(relationship_validation["errors"])
        warnings.extend(relationship_validation["warnings"])
        field_errors.update(relationship_validation["field_errors"])
        suggestions.extend(relationship_validation["suggestions"])
        
        # 4. Cross-validation (units vs relationships)
        cross_validation = await _validate_cross_references(
            request.units, request.relationships
        )
        errors.extend(cross_validation["errors"])
        warnings.extend(cross_validation["warnings"])
        field_errors.update(cross_validation["field_errors"])
        suggestions.extend(cross_validation["suggestions"])
        
        # 5. Business rule validation
        business_validation = await _validate_business_rules(
            request.units, request.relationships
        )
        errors.extend(business_validation["errors"])
        warnings.extend(business_validation["warnings"])
        field_errors.update(business_validation["field_errors"])
        suggestions.extend(business_validation["suggestions"])
        
        is_valid = len(errors) == 0
        
        result = {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "field_errors": field_errors,
            "suggestions": suggestions,
            "unit_count": len(request.units),
            "relationship_count": len(request.relationships)
        }
        
        logger.info(f"Validation completed: {'PASS' if is_valid else 'FAIL'} - {len(errors)} errors, {len(warnings)} warnings")
        return result
        
    except Exception as e:
        logger.error(f"Error during validation: {str(e)}", exc_info=True)
        return {
            "is_valid": False,
            "errors": [f"Validation system error: {str(e)}"],
            "warnings": [],
            "field_errors": {},
            "suggestions": ["Please try again or contact support"],
            "unit_count": len(request.units),
            "relationship_count": len(request.relationships)
        }


async def _validate_units(
    units: List[HarrisMatrixBulkCreateUnit],
    site_id: UUID,
    unit_resolver,
    db: AsyncSession
) -> Dict[str, Any]:
    """Validate individual units in the request."""
    errors = []
    warnings = []
    field_errors = {}
    suggestions = []
    
    # Check for duplicate temp_ids
    temp_ids = [unit.temp_id for unit in units]
    if len(temp_ids) != len(set(temp_ids)):
        duplicates = [tid for tid in temp_ids if temp_ids.count(tid) > 1]
        errors.append(f"Duplicate temporary IDs found: {list(set(duplicates))}")
        field_errors["units.temp_id"] = "Duplicate temporary IDs"
        suggestions.append("Ensure all temporary IDs are unique")
    
    # Validate each unit
    for i, unit in enumerate(units):
        unit_errors = []
        
        # Check temp_id format
        if not unit.temp_id or not unit.temp_id.strip():
            unit_errors.append("Temporary ID cannot be empty")
            field_errors[f"units[{i}].temp_id"] = "Required field"
        
        # Validate unit type
        if unit.unit_type not in ['us', 'usm']:
            unit_errors.append(f"Invalid unit type: {unit.unit_type}")
            field_errors[f"units[{i}].unit_type"] = "Invalid unit type"
            suggestions.append("Unit type must be 'us' or 'usm'")
        
        # Validate code if provided
        if unit.code:
            code_errors = await _validate_unit_code(
                unit.code, unit.unit_type, site_id, unit_resolver, i
            )
            unit_errors.extend(code_errors["errors"])
            field_errors.update(code_errors["field_errors"])
        
        # Validate US-specific fields
        if unit.unit_type == 'us' and unit.tipo and unit.tipo not in ['positiva', 'negativa']:
            unit_errors.append(f"Invalid US type: {unit.tipo}")
            field_errors[f"units[{i}].tipo"] = "Invalid US type"
            suggestions.append("US type must be 'positiva' or 'negativa'")
        
        # Validate USM-specific fields
        if unit.unit_type == 'usm' and unit.tipo:
            unit_errors.append("USM units should not have tipo field")
            field_errors[f"units[{i}].tipo"] = "Field not applicable to USM"
            suggestions.append("Remove tipo field for USM units")
        
        if unit_errors:
            errors.append(f"Unit {unit.temp_id}: {'; '.join(unit_errors)}")
    
    return {
        "errors": errors,
        "warnings": warnings,
        "field_errors": field_errors,
        "suggestions": suggestions
    }


async def _validate_unit_code(
    code: str,
    unit_type: str,
    site_id: UUID,
    unit_resolver,
    unit_index: int
) -> Dict[str, Any]:
    """Validate a single unit code using the resolver."""
    errors = []
    field_errors = {}
    
    try:
        # Basic format validation
        if not code or not code.strip():
            errors.append("Unit code cannot be empty")
            field_errors[f"units[{unit_index}].code"] = "Required field"
            return {"errors": errors, "field_errors": field_errors}
        
        code = code.strip().upper()
        
        # Check code format
        if unit_type == 'us':
            if not code.startswith('US'):
                warnings = [f"US code '{code}' should start with 'US'"]
                field_errors[f"units[{unit_index}].code"] = "Non-standard code format"
        elif unit_type == 'usm':
            if not code.startswith('USM'):
                warnings = [f"USM code '{code}' should start with 'USM'"]
                field_errors[f"units[{unit_index}].code"] = "Non-standard code format"
        
        # Check for conflicts using resolver
        resolved_id = await unit_resolver.resolve_unit_code(code, unit_type)
        if resolved_id:
            errors.append(f"Unit code '{code}' already exists in this site")
            field_errors[f"units[{unit_index}].code"] = "Code conflict"
        
        return {"errors": errors, "field_errors": field_errors, "warnings": warnings}
        
    except Exception as e:
        logger.error(f"Error validating unit code '{code}': {str(e)}")
        return {
            "errors": [f"Error validating code '{code}': {str(e)}"],
            "field_errors": {f"units[{unit_index}].code": "Validation error"}
        }


async def _validate_relationships(
    units: List[HarrisMatrixBulkCreateUnit],
    relationships: List[HarrisMatrixBulkCreateRelationship],
    unit_resolver
) -> Dict[str, Any]:
    """Validate relationships in the request."""
    errors = []
    warnings = []
    field_errors = {}
    suggestions = []
    
    # Get all unit temp_ids
    unit_temp_ids = {unit.temp_id for unit in units}
    
    # Check for duplicate relationship temp_ids
    rel_temp_ids = [rel.temp_id for rel in relationships]
    if len(rel_temp_ids) != len(set(rel_temp_ids)):
        duplicates = [tid for tid in rel_temp_ids if rel_temp_ids.count(tid) > 1]
        errors.append(f"Duplicate relationship temporary IDs found: {list(set(duplicates))}")
        field_errors["relationships.temp_id"] = "Duplicate temporary IDs"
        suggestions.append("Ensure all relationship temporary IDs are unique")
    
    # Validate each relationship
    for i, rel in enumerate(relationships):
        rel_errors = []
        
        # Check temp_id format
        if not rel.temp_id or not rel.temp_id.strip():
            rel_errors.append("Relationship temporary ID cannot be empty")
            field_errors[f"relationships[{i}].temp_id"] = "Required field"
        
        # Check source unit exists
        if rel.from_temp_id not in unit_temp_ids:
            rel_errors.append(f"Source unit '{rel.from_temp_id}' not found in units")
            field_errors[f"relationships[{i}].from_temp_id"] = "Invalid reference"
        
        # Check target unit exists
        if rel.to_temp_id not in unit_temp_ids:
            rel_errors.append(f"Target unit '{rel.to_temp_id}' not found in units")
            field_errors[f"relationships[{i}].to_temp_id"] = "Invalid reference"
        
        # Check for self-relationships
        if rel.from_temp_id == rel.to_temp_id:
            rel_errors.append("Unit cannot have relationship with itself")
            field_errors[f"relationships[{i}].to_temp_id"] = "Self-reference"
            suggestions.append("Remove self-references from relationships")
        
        # Validate relationship type
        valid_types = [
            'uguale_a', 'si_lega_a', 'gli_si_appoggia', 'si_appoggia_a',
            'coperto_da', 'copre', 'tagliato_da', 'taglia', 'riempito_da', 'riempie'
        ]
        if rel.relation_type.value not in valid_types:
            rel_errors.append(f"Invalid relationship type: {rel.relation_type.value}")
            field_errors[f"relationships[{i}].relation_type"] = "Invalid relationship type"
            suggestions.append(f"Valid types are: {', '.join(valid_types)}")
        
        if rel_errors:
            errors.append(f"Relationship {rel.temp_id}: {'; '.join(rel_errors)}")
    
    return {
        "errors": errors,
        "warnings": warnings,
        "field_errors": field_errors,
        "suggestions": suggestions
    }


async def _validate_cross_references(
    units: List[HarrisMatrixBulkCreateUnit],
    relationships: List[HarrisMatrixBulkCreateRelationship]
) -> Dict[str, Any]:
    """Validate cross-references between units and relationships."""
    errors = []
    warnings = []
    field_errors = {}
    
    # Check for orphaned units (units not referenced in any relationship)
    referenced_unit_ids = set()
    for rel in relationships:
        referenced_unit_ids.add(rel.from_temp_id)
        referenced_unit_ids.add(rel.to_temp_id)
    
    orphaned_units = [unit.temp_id for unit in units if unit.temp_id not in referenced_unit_ids]
    if orphaned_units:
        warnings.append(f"Units without relationships: {orphaned_units}")
        field_errors["relationships"] = "Orphaned units detected"
    
    # Check for empty relationships list when there are multiple units
    if len(units) > 1 and not relationships:
        warnings.append(f"Multiple units ({len(units)}) but no relationships defined")
        field_errors["relationships"] = "Missing relationships"
    
    return {
        "errors": errors,
        "warnings": warnings,
        "field_errors": field_errors,
        "suggestions": []
    }


async def _validate_business_rules(
    units: List[HarrisMatrixBulkCreateUnit],
    relationships: List[HarrisMatrixBulkCreateRelationship]
) -> Dict[str, Any]:
    """Validate business rules for stratigraphic relationships."""
    errors = []
    warnings = []
    field_errors = {}
    suggestions = []
    
    # Create lookup for unit types and properties
    unit_lookup = {unit.temp_id: unit for unit in units}
    
    for rel in relationships:
        from_unit = unit_lookup.get(rel.from_temp_id)
        to_unit = unit_lookup.get(rel.to_temp_id)
        
        if not from_unit or not to_unit:
            continue  # Already validated in _validate_relationships
        
        rel_type = rel.relation_type.value
        
        # Use centralized business rules validation
        try:
            StratigraphicRulesValidator.validate_single_relationship(
                from_unit, to_unit, rel_type
            )
        except Exception as e:
            errors.append(f"Relationship {rel.temp_id}: {str(e)}")
            field_errors[f"relationships.{rel.temp_id}"] = "Business rule violation"
            suggestions.append("Check unit types and relationship compatibility")
    
    return {
        "errors": errors,
        "warnings": warnings,
        "field_errors": field_errors,
        "suggestions": suggestions
    }


async def _detect_potential_cycles(
    units: List[HarrisMatrixBulkCreateUnit],
    relationships: List[HarrisMatrixBulkCreateRelationship]
) -> List[List[str]]:
    """
    Detect potential cycles in relationships before processing.
    
    Uses centralized cycle detection from stratigraphy_helpers.
    """
    try:
        # Convert units and relationships to validation format
        validation_units = []
        for unit in units:
            validation_units.append({
                'id': unit.temp_id,
                'unit_type': unit.unit_type,
                'unit': unit
            })
        
        validation_relationships = []
        for rel in relationships:
            validation_relationships.append({
                'from_unit_id': rel.from_temp_id,
                'to_unit_id': rel.to_temp_id,
                'relation_type': rel.relation_type.value
            })
        
        # Use centralized cycle detection
        cycles = CycleDetector.detect_cycles_from_relationships(validation_relationships)
        return cycles
        
    except Exception as e:
        logger.error(f"Error detecting cycles: {str(e)}")
        return []


# ===== NUOVI ENDPOINTS PER EDITOR GRAFICO =====

@router.post(
    "/sites/{site_id}/bulk-create",
    summary="Bulk create units and relationships for Harris Matrix editor",
    tags=["Harris Matrix Editor"]
)
async def v1_bulk_create_harris_matrix(
    site_id: UUID,
    request: HarrisMatrixBulkCreateRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixBulkCreateResponse:
    """
    Bulk create multiple US/USM units and their relationships with enhanced validation.

    This endpoint allows the Harris Matrix editor to create multiple units
    and establish relationships between them in a single atomic operation.
    Automatically generates sequential codes if not provided.

    Enhanced validation includes:
    - Comprehensive request structure validation
    - Unit code conflict detection using resolver
    - Circular reference detection
    - Relationship type validation
    - Detailed error responses for debugging

    Args:
        site_id: UUID of the archaeological site
        request: Bulk creation request with units and relationships
    
    Returns:
        Created units, relationships, and mapping information
    
    Raises:
        HTTPException: With detailed validation error information
    """
    try:
        logger.info(f"Bulk creating Harris Matrix for site_id: {site_id}")
        
        # 🔍 DEBUG: Log the exact request structure received
        logger.info(f"🔍 REQUEST DEBUG - Raw request structure:")
        logger.info(f"  - Request type: {type(request)}")
        logger.info(f"  - Request units field: {hasattr(request, 'units')}")
        logger.info(f"  - Request relationships field: {hasattr(request, 'relationships')}")
        logger.info(f"  - Request nodes field: {hasattr(request, 'nodes')}")
        logger.info(f"  - Request edges field: {hasattr(request, 'edges')}")
        
        # Log the actual content if available
        if hasattr(request, 'dict'):
            request_dict = request.dict()
            logger.info(f"🔍 REQUEST DICT KEYS: {list(request_dict.keys())}")
            
            if 'units' in request_dict:
                logger.info(f"  - Units count: {len(request_dict['units'])}")
                if request_dict['units']:
                    logger.info(f"  - Sample unit keys: {list(request_dict['units'][0].keys())}")
            
            if 'relationships' in request_dict:
                logger.info(f"  - Relationships count: {len(request_dict['relationships'])}")
                if request_dict['relationships']:
                    logger.info(f"  - Sample relationship keys: {list(request_dict['relationships'][0].keys())}")
                    
        # Try to log original units/edges if they exist
        if hasattr(request, 'dict') and 'nodes' in request.dict():
            logger.warning(f"⚠️  Found 'nodes' field instead of 'units'!")
            if 'edges' in request.dict():
                logger.warning(f"⚠️  Found 'edges' field instead of 'relationships'!")

        logger.info(f"Request contains {len(request.units)} units and {len(request.relationships)} relationships")

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

        # Initialize services for comprehensive validation
        harris_service = HarrisMatrixService(db)
        from app.services.harris_matrix_unit_resolver import UnitResolver
        unit_resolver = UnitResolver(db)

        # ===== COMPREHENSIVE PRE-VALIDATION =====
        
        # 1. Validate request structure and content
        validation_result = await _validate_bulk_create_request(
            request, site_id, unit_resolver, db
        )
        
        if not validation_result["is_valid"]:
            logger.error(f"Request validation failed for site {site_id}: {validation_result['errors']}")
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Request validation failed",
                    "validation_errors": validation_result["errors"],
                    "validation_warnings": validation_result.get("warnings", []),
                    "field_errors": validation_result.get("field_errors", {}),
                    "suggestions": validation_result.get("suggestions", [])
                }
            )

        # 2. Check for circular references before processing
        cycles = await _detect_potential_cycles(request.units, request.relationships)
        if cycles:
            logger.warning(f"Circular references detected in request for site {site_id}: {cycles}")
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Circular references detected in relationships",
                    "cycles": cycles,
                    "field": "relationships",
                    "suggestion": "Remove circular references before submitting"
                }
            )

        # ===== PROCEED WITH BULK CREATION =====
        
        # Convert Pydantic models to dictionaries for service
        # Use the properly authenticated user ID from dependency injection
        logger.debug(f"DEBUG: Using current_user_id from auth dependency: {current_user_id}")
        
        units_data = []
        for unit in request.units:
            unit_dict = unit.dict(exclude_none=True)
            # Always set created_by: current authenticated user
            unit_dict['created_by'] = str(current_user_id)
            unit_dict['updated_by'] = str(current_user_id)
            logger.debug(f"DEBUG: Unit {unit.temp_id} created_by set to: {unit_dict['created_by']}")
            logger.debug(f"DEBUG: Unit {unit.temp_id} updated_by set to: {unit_dict['updated_by']}")
            units_data.append(unit_dict)
        
        relationships_data = [rel.dict() for rel in request.relationships]
        
        # Perform bulk creation with pre-validated data
        result = await harris_service.bulk_create_units_with_relationships(
            site_id=site_id,
            units_data=units_data,
            relationships_data=relationships_data,
            current_user_id=current_user_id
        )
        
        # ===== CRITICAL FIX: Match response to frontend expectations =====
        response = HarrisMatrixBulkCreateResponse(
            success=True,
            message=f"Successfully created {result['created_units']} units and {result['created_relationships']} relationships",
            site_id=site_id,
            created_units=result['created_units'],  # INT count
            created_relationships=result['created_relationships'],  # INT count
            unit_mapping=result['unit_mapping'],  # Frontend uses this CRITICAL
            relationship_mapping=result.get('relationship_mapping', {}),
            units=result['units'] if 'units' in result else result.get('created_units_list', []),  # UnitResponse data
            relationships=result['relationships'] if 'relationships' in result else result.get('created_relationships_list', []),  # RelationshipResponse data
            validation_result=validation_result.get("pydantic_result")
        )
        
        logger.info(f"Bulk creation completed successfully for site {site_id}: {response.message}")
        return response
    
    except BusinessLogicError as e:
        logger.error(f"Business logic error in bulk creation for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": e.message,
                "type": "business_logic_error",
                "field": getattr(e, 'field', None),
                "suggestion": "Review business rules and data requirements"
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions (including our enhanced ones)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in bulk creation for site {site_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error during bulk creation",
                "type": "internal_error",
                "details": str(e),
                "suggestion": "Please try again or contact support if the issue persists"
            }
        )


@router.put(
    "/sites/{site_id}/bulk-update",
    summary="Bulk update relationships for a unit",
    tags=["Harris Matrix Editor"]
)
async def v1_bulk_update_harris_matrix(
    site_id: UUID,
    request: HarrisMatrixBulkUpdateRequest,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixBulkUpdateResponse:
    """
    Bulk update relationships for a specific unit.

    This endpoint allows the Harris Matrix editor to update all relationships
    for a specific unit in a single operation, ensuring consistency
    and validation of the updated relationships.

    Args:
        site_id: UUID of the archaeological site
        request: Bulk update request with unit ID and new relationships
    
    Returns:
        Update results with old and new relationship data
    """
    try:
        logger.info(f"Bulk updating Harris Matrix for unit {request.unit_id} in site {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Convert relationship enum keys to strings for service
        relationships_update = {
            rel_type.value: targets for rel_type, targets in request.relationships.items()
        }
        
        # Initialize service and perform bulk update with proper transaction handling
        harris_service = HarrisMatrixService(db)
        
        # Use transaction with rollback on validation failure
        async with db.begin() as transaction:
            try:
                result = await harris_service.bulk_update_relationships(
                    site_id=site_id,
                    unit_id=request.unit_id,
                    unit_type=request.unit_type.value,
                    relationships_update=relationships_update
                )
                # Transaction will commit automatically if no exceptions
            except (StratigraphicCycleDetected, InvalidStratigraphicRelation, HarrisMatrixValidationError) as e:
                # Validation failed - transaction will be rolled back automatically
                logger.error(f"Bulk update validation failed for unit {request.unit_id}: {str(e)}")
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "Validation failed - transaction rolled back",
                        "type": "validation_error",
                        "validation_error": str(e),
                        "unit_id": str(request.unit_id),
                        "unit_type": request.unit_type.value,
                        "suggestion": "Review the relationships and try again"
                    }
                )
        
        # Convert back to enum keys for response
        new_relationships_enum = {
            StratigraphicRelation(rel_type): targets
            for rel_type, targets in result['new_relationships'].items()
        }
        old_relationships_enum = {
            StratigraphicRelation(rel_type): targets
            for rel_type, targets in result['old_relationships'].items()
        }
        
        response = HarrisMatrixBulkUpdateResponse(
            success=True,
            message=f"Updated {result['updated_relationships']} relationship types for {request.unit_type.value.upper()}{result.get('unit_code', '')}",
            site_id=site_id,
            unit_id=request.unit_id,
            unit_type=request.unit_type,
            updated_relationships=result['updated_relationships'],
            old_relationships=old_relationships_enum,
            new_relationships=new_relationships_enum
        )
        
        logger.info(f"Bulk update completed successfully for unit {request.unit_id}")
        return response
        
    except BusinessLogicError as e:
        logger.error(f"Business logic error in bulk update for unit {request.unit_id}: {str(e)}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error in bulk update for unit {request.unit_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.delete(
    "/sites/{site_id}/units/{unit_id}",
    summary="Delete a unit with relationship cleanup",
    tags=["Harris Matrix Editor"]
)
async def v1_delete_harris_matrix_unit(
    site_id: UUID,
    unit_id: UUID,
    unit_type: UnitTypeEnum = Query(..., description="Unit type: 'us' or 'usm'"),
    cleanup_references: bool = Query(True, description="Whether to cleanup references from other units"),
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixDeleteResponse:
    """
    Delete a unit with proper cleanup of relationships.

    This endpoint allows the Harris Matrix editor to delete a unit and
    optionally remove all references to it from other units' relationships,
    maintaining the integrity of the Harris Matrix.

    Args:
        site_id: UUID of the archaeological site
        unit_id: UUID of the unit to delete
        unit_type: Type of unit ('us' or 'usm')
        cleanup_references: Whether to cleanup references from other units
        
    Returns:
        Deletion results with cleanup information
    """
    try:
        logger.info(f"Deleting {unit_type.value} unit {unit_id} from site {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Initialize service and perform deletion with cleanup
        harris_service = HarrisMatrixService(db)
        result = await harris_service.delete_unit_with_cleanup(
            site_id=site_id,
            unit_id=unit_id,
            unit_type=unit_type.value
        )
        
        response = HarrisMatrixDeleteResponse(
            success=True,
            message=f"Deleted {unit_type.value.upper()} {result['deleted_unit']['code']} with reference cleanup",
            site_id=site_id,
            deleted_unit=result['deleted_unit'],
            cleaned_references=result['cleaned_references'],
            affected_units_count=result.get('affected_units_count', 0)
        )
        
        logger.info(f"Unit deletion completed successfully: {result['deleted_unit']['code']}")
        return response
        
    except BusinessLogicError as e:
        logger.error(f"Business logic error in unit deletion for {unit_id}: {str(e)}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error in unit deletion for {unit_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/validate",
    summary="Validate Harris Matrix relationships",
    tags=["Harris Matrix Editor"]
)
async def v1_validate_harris_matrix(
    site_id: UUID,
    request: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixValidationResult:
    """
    Validate Harris Matrix relationships for business rules and cycles.

    This endpoint validates the current Harris Matrix structure or a provided
    set of relationships against business rules and checks for cycles
    in the stratigraphic graph.

    Args:
        site_id: UUID of the archaeological site
        request: Optional dictionary with specific validation data
        
    Returns:
        Validation results with errors, warnings, and cycle information
    """
    try:
        logger.info(f"Validating Harris Matrix for site_id: {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Get current Harris Matrix data
        harris_service = HarrisMatrixService(db)
        matrix_data = await harris_service.generate_harris_matrix(site_id)
        
        # Build validation data structure
        units = matrix_data.get('nodes', [])
        edges = matrix_data.get('edges', [])
        
        # Convert to validation format
        validation_units = []
        for unit in units:
            unit_data = {
                'id': unit['data']['id'],
                'unit_type': unit['type'],
                'unit': unit  # Pass the full unit data for validation
            }
            validation_units.append(unit_data)
        
        validation_relationships = []
        for edge in edges:
            rel_data = {
                'from_unit_id': edge['from'],
                'to_unit_id': edge['to'],
                'relation_type': edge['type']
            }
            validation_relationships.append(rel_data)
        
        # Perform validation
        await harris_service.validate_stratigraphic_relationships(
            validation_units, validation_relationships
        )
        
        # Detect cycles
        graph = harris_service._build_validation_graph(validation_units, validation_relationships)
        cycles = harris_service.detect_cycles_in_graph(graph)
        
        # Build validation result
        validation_result = HarrisMatrixValidationResult(
            is_valid=len(cycles) == 0,
            errors=[],
            warnings=[],
            cycles=[[unit for unit in cycle] for cycle in cycles]
        )
        
        # Add warnings for potential issues
        if len(units) > 100:
            validation_result.warnings.append("Large number of units may impact performance")
        
        if len(edges) > len(units) * 2:
            validation_result.warnings.append("High density of relationships detected")
        
        logger.info(f"Validation completed for site {site_id}: {len(cycles)} cycles detected")
        return validation_result
        
    except StratigraphicCycleDetected as e:
        logger.warning(f"Cycles detected in Harris Matrix for site {site_id}: {str(e)}")
        return HarrisMatrixValidationResult(
            is_valid=False,
            errors=[str(e)],
            warnings=[],
            cycles=[e.cycle_path] if e.cycle_path else []
        )
    except BusinessLogicError as e:
        logger.error(f"Business logic error in validation for site {site_id}: {str(e)}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error in validation for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/validate-relationship",
    summary="Validate a single stratigraphic relationship",
    tags=["Harris Matrix Editor"]
)
async def v1_validate_relationship(
    site_id: UUID,
    request: RelationshipValidation,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixValidationResult:
    """
    Validate a single stratigraphic relationship against business rules.

    This endpoint allows the Harris Matrix editor to validate individual
    relationships before adding them to ensure they follow business rules
    and stratigraphic principles.

    Args:
        site_id: UUID of the archaeological site
        request: Relationship validation request
        
    Returns:
        Validation result for the specific relationship
    """
    try:
        logger.info(f"Validating relationship {request.from_unit_code} -> {request.to_unit_code} ({request.relation_type})")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Find the units
        harris_service = HarrisMatrixService(db)
        
        # Use centralized unit lookup for both source and target units
        unit_lookup = UnitLookupService(db)
        
        from_unit = await unit_lookup.get_unit_by_code(
            site_id, request.from_unit_code, request.from_unit_type.value
        )
        to_unit = await unit_lookup.get_unit_by_code(
            site_id, request.to_unit_code, request.to_unit_type.value
        )
        
        if not from_unit:
            return HarrisMatrixValidationResult(
                is_valid=False,
                errors=[f"Source unit {request.from_unit_type.value.upper()}{request.from_unit_code} not found"],
                warnings=[],
                cycles=[]
            )
        
        if not to_unit:
            return HarrisMatrixValidationResult(
                is_valid=False,
                errors=[f"Target unit {request.to_unit_type.value.upper()}{request.to_unit_code} not found"],
                warnings=[],
                cycles=[]
            )
        
        # Additional business rule validation
        errors = []
        warnings = []
        
        # Check self-relationship (handle both database models and bulk creation objects)
        def get_unit_id(unit):
            """Get unit ID from either database model (.id) or bulk creation object (.temp_id)"""
            if hasattr(unit, 'temp_id'):
                return unit.temp_id
            elif hasattr(unit, 'id'):
                return unit.id
            else:
                raise ValueError(f"Unit object has no 'id' or 'temp_id' attribute: {unit}")
        
        if get_unit_id(from_unit) == get_unit_id(to_unit):
            errors.append("Unit cannot have relationship with itself")
        
        # Validate the relationship using the centralized service
        try:
            await harris_service.validate_single_relationship(
                from_unit, to_unit, request.relation_type.value
            )
        except InvalidStratigraphicRelation as e:
            errors.append(str(e))
        
        validation_result = HarrisMatrixValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            cycles=[]
        )
        
        logger.info(f"Relationship validation completed: {validation_result.is_valid}")
        return validation_result
        
    except BusinessLogicError as e:
        logger.error(f"Business logic error in relationship validation: {str(e)}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error in relationship validation: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/detect-cycles",
    summary="Detect cycles in Harris Matrix relationships",
    tags=["Harris Matrix Editor"]
)
async def v1_detect_harris_matrix_cycles(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> CycleDetectionResult:
    """
    Detect cycles in Harris Matrix stratigraphic relationships.

    This endpoint analyzes the current Harris Matrix structure to identify
    any cycles in the stratigraphic graph, which would indicate
    logical inconsistencies in the relationships.

    Args:
        site_id: UUID of the archaeological site
        
    Returns:
        Cycle detection results with affected units
    """
    try:
        logger.info(f"Detecting cycles in Harris Matrix for site_id: {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        # Get current Harris Matrix data
        harris_service = HarrisMatrixService(db)
        matrix_data = await harris_service.generate_harris_matrix(site_id)
        
        # Build graph for cycle detection
        nodes = matrix_data.get('nodes', [])
        edges = matrix_data.get('edges', [])
        
        # Convert to validation format
        validation_units = [
            {'id': unit['data']['id'], 'unit_type': unit['type'], 'unit': unit}
            for unit in nodes
        ]
        
        validation_relationships = [
            {
                'from_unit_id': edge['from'],
                'to_unit_id': edge['to'],
                'relation_type': edge['type']
            }
            for edge in edges
        ]
        
        # Build graph and detect cycles
        graph = harris_service._build_validation_graph(validation_units, validation_relationships)
        cycles = harris_service.detect_cycles_in_graph(graph)
        
        # Get affected units
        affected_units = set()
        for cycle in cycles:
            affected_units.update(cycle)
        
        cycle_result = CycleDetectionResult(
            has_cycles=len(cycles) > 0,
            cycles=[[unit for unit in cycle] for cycle in cycles],
            cycle_count=len(cycles),
            affected_units=list(affected_units)
        )
        
        logger.info(f"Cycle detection completed for site {site_id}: {len(cycles)} cycles found")
        return cycle_result
        
    except Exception as e:
        logger.error(f"Error in cycle detection for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/validate-code",
    summary="Validate unit code availability",
    tags=["Harris Matrix Editor"]
)
async def v1_validate_unit_code(
    site_id: UUID,
    request: UnitCodeValidation,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> HarrisMatrixValidationResult:
    """
    Validate if a unit code is available for use.

    This endpoint allows the Harris Matrix editor to check if a proposed
    unit code is already in use or follows the correct format before
    creating a new unit.

    Args:
        site_id: UUID of the archaeological site
        request: Unit code validation request
        
    Returns:
        Validation result for the unit code
    """
    try:
        logger.info(f"Validating unit code {request.code} for site {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(
                status_code=403,
                detail="Access denied to this site"
            )
        
        errors = []
        warnings = []
        
        # Check code format
        if request.unit_type == UnitTypeEnum.US:
            if not request.code.startswith('US'):
                errors.append("US codes should start with 'US'")
            if len(request.code) < 3:
                errors.append("US codes should be at least 3 characters long")
        else:  # USM
            if not request.code.startswith('USM'):
                errors.append("USM codes should start with 'USM'")
            if len(request.code) < 4:
                errors.append("USM codes should be at least 4 characters long")
        
        # Check if code already exists
        harris_service = HarrisMatrixService(db)
        
        # Use centralized unit lookup to check if code exists
        unit_lookup = UnitLookupService(db)
        existing_unit = await unit_lookup.get_unit_by_code(
            site_id, request.code, request.unit_type.value
        )
        
        if existing_unit:
            errors.append(f"Unit code {request.code} is already in use")
        
        # Check for similar codes using unit lookup service
        us_units, usm_units = await unit_lookup.get_units_by_site(site_id)
        
        similar_codes = []
        if request.unit_type == UnitTypeEnum.US:
            code_num = request.code[2:] if len(request.code) > 2 else ""
            for us in us_units:
                if code_num and code_num in us.us_code and us.us_code != request.code:
                    similar_codes.append(us.us_code)
        else:  # USM
            code_num = request.code[3:] if len(request.code) > 3 else ""
            for usm in usm_units:
                if code_num and code_num in usm.usm_code and usm.usm_code != request.code:
                    similar_codes.append(usm.usm_code)
        
        if similar_codes:
            warnings.append(f"Similar codes found that might cause confusion: {', '.join(similar_codes[:3])}")
        
        validation_result = HarrisMatrixValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            cycles=[]
        )
        
        logger.info(f"Unit code validation completed for {request.code}: {validation_result.is_valid}")
        return validation_result
        
    except Exception as e:
        logger.error(f"Error in unit code validation for {request.code}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/layout",
    summary="Save Harris Matrix node positions",
    tags=["Harris Matrix Editor"]
)
async def v1_save_harris_matrix_layout(
    site_id: str,
    request: HarrisMatrixLayoutSaveRequest,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Save node positions for Harris Matrix layout.

    This endpoint saves the X,Y coordinates of all nodes in the Harris Matrix
    editor, allowing the layout to be restored when reloading.
    """
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Access denied to this site")

    try:
        # Delete existing positions for this site
        await db.execute(
            delete(HarrisMatrixLayout).where(
                HarrisMatrixLayout.site_id == site_id
            )
        )

        # Insert new positions
        saved_count = 0
        for pos in request.positions:
            layout = HarrisMatrixLayout(
                site_id=site_id,
                unit_id=pos.unit_id,
                unit_type=pos.unit_type,
                x=pos.x,
                y=pos.y
            )
            db.add(layout)
            saved_count += 1

        await db.commit()

        logger.info(f"Saved {saved_count} node positions for site {site_id}")
        return {
            "success": True,
            "saved_positions": saved_count,
            "site_id": site_id
        }

    except Exception as e:
        logger.error(f"Error saving layout for site {site_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error saving layout: {str(e)}"
        )


@router.get(
    "/sites/{site_id}/layout",
    summary="Get Harris Matrix node positions",
    tags=["Harris Matrix Editor"]
)
async def v1_get_harris_matrix_layout(
    site_id: str,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Get saved node positions for Harris Matrix layout.

    Returns the saved X,Y coordinates for all nodes, allowing the editor
    to restore the previous layout.
    """
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Access denied to this site")

    try:
        result = await db.execute(
            select(HarrisMatrixLayout).where(
                HarrisMatrixLayout.site_id == site_id
            )
        )
        layouts = result.scalars().all()

        positions = [
            {
                "unit_id": layout.unit_id,
                "unit_type": layout.unit_type,
                "x": layout.x,
                "y": layout.y
            }
            for layout in layouts
        ]

        logger.info(f"Retrieved {len(positions)} node positions for site {site_id}")
        return {
            "site_id": site_id,
            "positions": positions,
            "count": len(positions)
        }

    except Exception as e:
        logger.error(f"Error getting layout for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting layout: {str(e)}"
        )


@router.get(
    "/sites/{site_id}/fallback-layout",
    summary="Generate complete fallback layout based on stratigraphic relationships",
    tags=["Harris Matrix Editor"]
)
async def v1_generate_fallback_layout(
    site_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Generate complete fallback layout based on stratigraphic relationships.
    
    This endpoint provides a comprehensive fallback layout generation service
    that analyzes all US/USM units and their relationships to create
    logical X,Y positions when no manual positioning is available.
    """
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Access denied to this site")

    try:
        logger.info(f"Generating fallback layout for site {site_id}")
        
        # Initialize service and get matrix data
        harris_service = HarrisMatrixService(db)
        matrix_data = await harris_service.generate_harris_matrix(site_id)
        
        nodes = matrix_data.get('nodes', [])
        relationships = matrix_data.get('edges', [])
        
        if not nodes:
            logger.warning(f"No nodes found for site {site_id}")
            return {
                "success": False,
                "message": "No stratigraphic units found for this site",
                "positions": []
            }
        
        # Check if nodes already have positions
        nodes_without_positions = [node for node in nodes if not node.get('position')]
        
        if not nodes_without_positions:
            logger.info(f"All nodes for site {site_id} already have positions")
            return {
                "success": True,
                "message": "All nodes already have positions",
                "positions": []
            }
        
        # Generate fallback positions
        fallback_positions = await harris_service._calculate_fallback_positions(
            site_id, nodes_without_positions, relationships
        )
        
        # Convert to API format
        positions = []
        for unit_id, position in fallback_positions.items():
            node = next((n for n in nodes_without_positions
                       if (n.get("label") or n.get("id")) == unit_id), None)
            
            if node:
                positions.append({
                    "unit_id": unit_id,
                    "unit_type": node.get("type", "us"),
                    "unit_code": node.get("label", unit_id),
                    "x": position["x"],
                    "y": position["y"]
                })
        
        return {
            "success": True,
            "message": f"Generated {len(positions)} fallback positions",
            "site_id": str(site_id),
            "total_nodes": len(nodes),
            "positioned_nodes": len(positions),
            "positions": positions
        }
        
    except Exception as e:
        logger.error(f"Error generating fallback layout for site {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating fallback layout: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/bulk-update-sequenza-fisica",
    summary="Bulk update sequenza_fisica based on physical order",
    tags=["Harris Matrix Editor"]
)
async def v1_bulk_update_sequenza_fisica(
    site_id: str,
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist)
) -> Dict[str, Any]:
    """
    Bulk update sequenza_fisica for multiple units based on physical order.
    
    This endpoint updates the sequenza_fisica JSON field for multiple units
    based on their physical arrangement in the Harris Matrix editor.
    """
    if not await verify_site_access(site_id, user_sites):
        raise HTTPException(status_code=403, detail="Access denied to this site")

    try:
        logger.info(f"Bulk updating sequenza_fisica for site {site_id}")
        
        updates = request.get('updates', {})
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        updated_units = 0
        errors = []
        
        async with db.begin():
            for unit_id, update_data in updates.items():
                try:
                    # Determine unit type and fetch the appropriate unit
                    unit = await _fetch_unit_by_temp_id(db, site_id, unit_id)
                    if not unit:
                        errors.append(f"Unit {unit_id} not found")
                        continue
                    
                    # Update sequenza_fisica
                    new_sequenza_fisica = update_data.get('sequenza_fisica', {})
                    if new_sequenza_fisica:
                        unit.sequenza_fisica = new_sequenza_fisica
                        updated_units += 1
                        logger.debug(f"Updated sequenza_fisica for unit {unit_id}")
                    
                except Exception as e:
                    error_msg = f"Error updating unit {unit_id}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        result = {
            "success": len(errors) == 0,
            "site_id": site_id,
            "updated_units": updated_units,
            "total_requested": len(updates),
            "errors": errors,
            "message": f"Updated sequenza_fisica for {updated_units} units"
        }
        
        logger.info(f"Bulk sequenza_fisica update completed: {result}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk sequenza_fisica update for site {site_id}: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error updating sequenza_fisica: {str(e)}"
        )


@router.post("/sites/{site_id}/bulk-update-sequenza-fisica-units", summary="Bulk update sequenzafisica for existing units")
async def v1_bulk_update_sequenza_fisica_units(
    site_id: UUID,
    request: SequenzaFisicaBulkUpdateRequest,
    db: AsyncSession = Depends(get_async_session),
    user_sites: list = Depends(get_current_user_sites_with_blacklist),
) -> Dict[str, Any]:
    """
    Update sequenzafisica field for multiple existing US/USM units.
    
    This endpoint is used by the Harris Matrix editor when modifying relationships
    of existing units without creating new ones.
    
    Args:
        site_id: UUID of the archaeological site
        request: Dictionary mapping unit IDs to their new sequenzafisica
        
    Returns:
        Dictionary with update statistics
    """
    try:
        logger.info(f"Bulk updating sequenzafisica for {len(request.updates)} units in site {site_id}")
        
        # Verify site access
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Access denied to this site")
        
        # Initialize service
        harris_service = HarrisMatrixService(db)
        
        # FastAPI dependency injection already handles the transaction
        # No need for nested transaction - this fixes the "A transaction is already begun" error
        result = await harris_service.bulk_update_sequenza_fisica_units(
            site_id=site_id,
            updates=request.updates
        )
        
        logger.info(f"Bulk sequenzafisica update completed: {result}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk sequenzafisica update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/sites/{site_id}/atomic-save",
    summary="Atomically save Harris Matrix with units, relationships, and layout",
    tags=["Harris Matrix Editor"]
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
        # Stampa in console dei dati ricevuti dall'endpoint
        print(f"\n=== DEBUG: DATI RICEVUTI DA ATOMIC-SAVE ===")
        print(f"Site ID: {site_id}")
        print(f"User ID: {current_user_id}")
        print(f"Request type: {type(request)}")
        
        # Stampa il contenuto completo della richiesta
        if hasattr(request, 'dict'):
            request_dict = request.dict()
            print(f"Request keys: {list(request_dict.keys())}")
            
            # Stampa dettagli sui nuovi units se presenti
            if 'new_units' in request_dict and request_dict['new_units']:
                new_units = request_dict['new_units']
                print(f"New units: {new_units}")
                if hasattr(new_units, 'units') and new_units.units:
                    print(f"Number of new units: {len(new_units.units)}")
                    for i, unit in enumerate(new_units.units):
                        print(f"  Unit {i+1}: {unit}")
                if hasattr(new_units, 'relationships') and new_units.relationships:
                    print(f"Number of new relationships: {len(new_units.relationships)}")
                    for i, rel in enumerate(new_units.relationships):
                        print(f"  Relationship {i+1}: {rel}")
            
            # Stampa dettagli sugli aggiornamenti se presenti
            if 'existing_units_updates' in request_dict and request_dict['existing_units_updates']:
                existing_updates = request_dict['existing_units_updates']
                print(f"Existing units updates: {existing_updates}")
                if hasattr(existing_updates, 'updates') and existing_updates.updates:
                    print(f"Number of existing unit updates: {len(existing_updates.updates)}")
                    for unit_id, update_data in existing_updates.updates.items():
                        print(f"  Update for {unit_id}: {update_data}")
            
            # Stampa dettagli sul layout se presente
            if 'layout_positions' in request_dict and request_dict['layout_positions']:
                layout = request_dict['layout_positions']
                print(f"Layout positions: {layout}")
                if hasattr(layout, 'positions') and layout.positions:
                    print(f"Number of layout positions: {len(layout.positions)}")
                    for i, pos in enumerate(layout.positions):
                        print(f"  Position {i+1}: unit_id={pos.unit_id}, x={pos.x}, y={pos.y}")
        
        print(f"=== FINE DEBUG DATI RICEVUTI ===\n")
        
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
        from datetime import datetime
        session_id = x_session_id or f"atomic-save-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(current_user_id)[:8]}"
        
        # Initialize services
        harris_service = HarrisMatrixService(db)
        mapping_service = HarrisMatrixMappingService(db)
        validation_service = HarrisMatrixValidationService()
        
        # Create mapping session
        transaction_id = await mapping_service.create_mapping_session(
            site_id=site_id,
            session_id=session_id,
            user_id=current_user_id
        )
        
        logger.info(f"Created mapping session: {transaction_id} for session: {session_id}")
        
        # ATOMIC TRANSACTION: All operations must succeed or none
        # Note: We use implicit transaction management here. The session already has
        # an active transaction from the mapping service operations. Using explicit
        # db.begin() would cause "A transaction is already begun on this Session" error.
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
                    
                    # STEP 1A: Pre-validation for duplicate detection
                    logger.info("Performing pre-validation for duplicate unit codes")
                    duplicate_validation = await validation_service.validate_duplicate_unit_codes(
                        site_id=site_id,
                        units_data=units_data,
                        db_session=db
                    )
                    
                    if not duplicate_validation["can_proceed"]:
                        logger.error(f"Duplicate unit codes detected: {duplicate_validation['duplicates']}")
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "error": "Duplicate unit codes detected",
                                "type": "validation_error",
                                "error_type": "duplicate_codes",
                                "details": duplicate_validation,
                                "suggestions": duplicate_validation.get("suggestions", []),
                                "step": "pre_validation"
                            }
                        )
                    
                    # STEP 1B: Validate relationship integrity if relationships exist
                    if relationships_data:
                        units_mapping = {unit["code"]: unit.get("temp_id") for unit in units_data if unit.get("code")}
                        logger.info("Validating relationship integrity")
                        relation_validation = await validation_service.validate_relationship_integrity(
                            site_id=site_id,
                            relationships_data=relationships_data,
                            units_mapping=units_mapping,
                            db_session=db
                        )
                        
                        if not relation_validation["can_proceed"]:
                            logger.error(f"Invalid relationships detected: {relation_validation['missing_units']}")
                            raise HTTPException(
                                status_code=422,
                                detail={
                                    "error": "Invalid relationships detected",
                                    "type": "validation_error",
                                    "error_type": "invalid_relations",
                                    "details": relation_validation,
                                    "suggestions": relation_validation.get("suggestions", []),
                                    "step": "relationship_validation"
                                }
                            )
                    
                    # STEP 1C: Detect potential cycles
                    if relationships_data:
                        logger.info("Detecting potential cycles in relationships")
                        cycle_validation = await validation_service.detect_potential_cycles(
                            relationships=relationships_data,
                            units_mapping=units_mapping
                        )
                        
                        if not cycle_validation["can_proceed"]:
                            logger.error(f"Potential cycles detected: {cycle_validation['cycle_paths']}")
                            raise HTTPException(
                                status_code=422,
                                detail={
                                    "error": "Potential cycles detected in relationships",
                                    "type": "validation_error",
                                    "error_type": "cycles_detected",
                                    "details": cycle_validation,
                                    "suggestions": cycle_validation.get("suggestions", []),
                                    "step": "cycle_detection"
                                }
                            )
                    
                    logger.info("Pre-validation passed, proceeding with bulk creation")
                    
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
                    
                    # Enhanced stale reference validation before bulk update
                    logger.info("STEP 2A: Performing stale reference validation")
                    validation_result = await validation_service.validate_stale_references(
                        site_id=site_id,
                        updates=updates_dict,
                        db_session=db
                    )
                    
                    if not validation_result["can_proceed"]:
                        logger.error(f"Stale references detected: {validation_result}")
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error_type": "stale_references",
                                "message": "Some units cannot be updated due to stale references",
                                "missing_units": validation_result["missing_ids"],
                                "soft_deleted_units": validation_result["soft_deleted_ids"],
                                "invalid_site_units": validation_result["wrong_site_ids"],
                                "recovery_suggestions": [
                                    "Remove references to non-existent units",
                                    "Restore soft-deleted units if needed",
                                    "Verify unit IDs are correct"
                                ],
                                "validation_time": validation_result.get("validation_time"),
                                "step": "stale_reference_validation"
                            }
                        )
                    
                    # Comprehensive bulk update integrity validation
                    logger.info("STEP 2B: Performing comprehensive bulk update integrity validation")
                    integrity_result = await validation_service.validate_bulk_update_integrity(
                        site_id=site_id,
                        updates=updates_dict,
                        db_session=db
                    )
                    
                    if not integrity_result["can_proceed"]:
                        logger.error(f"Bulk update integrity validation failed: {integrity_result}")
                        # Collect all issues for detailed error response
                        all_issues = []
                        
                        if integrity_result["invalid_data"]:
                            all_issues.extend([
                                f"Invalid data: {issue['unit_id']} - {issue['reason']}"
                                for issue in integrity_result["invalid_data"]
                            ])
                        
                        if integrity_result["relationship_issues"]:
                            all_issues.extend([
                                f"Relationship issue: {issue['unit_id']} - {issue['reason']}"
                                for issue in integrity_result["relationship_issues"]
                            ])
                        
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "error": "Bulk update integrity validation failed",
                                "type": "integrity_validation_error",
                                "details": {
                                    "invalid_data": integrity_result["invalid_data"],
                                    "relationship_issues": integrity_result["relationship_issues"],
                                    "suggestions": integrity_result.get("suggestions", [])
                                },
                                "suggestions": [
                                    "Fix invalid data format in sequenza_fisica updates",
                                    "Fix references to non-existent unit codes"
                                ],
                                "step": "integrity_validation"
                            }
                        )
                    
                    # Perform enhanced bulk update within the transaction
                    logger.info("STEP 2C: Performing enhanced bulk update")
                    update_result = await harris_service.bulk_update_sequenza_fisica_units(
                        site_id=site_id,
                        updates=updates_dict
                    )
                    
                    operation_results["existing_units_updated"] = update_result.get('updated_count', 0)
                    
                    # Include skipped units and validation details in response tracking
                    if update_result.get('skipped_units'):
                        operation_results["skipped_units"] = update_result['skipped_units']
                        logger.warning(f"Skipped {len(update_result['skipped_units'])} units during bulk update")
                    
                    if update_result.get('validation_details'):
                        operation_results["validation_details"] = update_result['validation_details']
                        logger.info("Validation details included in operation results")
                    
                    logger.info(f"Successfully updated relationships for {operation_results['existing_units_updated']} existing units")
                    
                except StaleReferenceError as e:
                    # Handle specific stale reference errors from service
                    logger.error(f"Stale reference error in bulk update: {e.message}")
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error_type": "stale_references",
                            "message": e.message,
                            "missing_units": e.missing_units,
                            "soft_deleted_units": e.soft_deleted_units,
                            "invalid_site_units": e.wrong_site_units,
                            "recovery_suggestions": e.recovery_suggestions,
                            "step": "bulk_update_stale_references"
                        }
                    )
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
                    
                    # Insert new positions
                    saved_count = 0
                    for pos in layout_positions.positions:
                        layout = HarrisMatrixLayout(
                            site_id=str(site_id),
                            unit_id=pos.unit_id,
                            unit_type=pos.unit_type,
                            x=pos.x,
                            y=pos.y
                        )
                        db.add(layout)
                        saved_count += 1
                    
                    await db.flush()  # Ensure layout data is written
                    operation_results["layout_positions_saved"] = saved_count
                    
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
            
            # All operations completed successfully - commit the transaction explicitly
            await db.commit()
            logger.info("Atomic transaction committed successfully")
            
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
            # Rollback transaction and mappings before re-raising
            await db.rollback()
            try:
                await mapping_service.rollback_mappings(site_id=site_id, session_id=session_id)
                logger.info(f"Rolled back mappings for session {session_id} due to HTTPException")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback mappings: {str(rollback_error)}")
            raise
            
        except Exception as e:
            # Any other exception - rollback the transaction
            await db.rollback()
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
    tags=["Harris Matrix Editor"]
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


async def _fetch_unit_by_temp_id(db: AsyncSession, site_id: str, temp_id: str):
    """
    Fetch unit by temp_id, checking both US and USM tables.
    
    Args:
        db: Database session
        site_id: Site ID
        temp_id: Temporary ID from frontend
        
    Returns:
        Unit object or None if not found
    """
    try:
        # Try US table first
        us_query = select(UnitaStratigrafica).where(
            and_(
                UnitaStratigrafica.site_id == site_id,
                UnitaStratigrafica.id == temp_id,
                UnitaStratigrafica.deleted_at.is_(None)
            )
        )
        us_result = await db.execute(us_query)
        us_unit = us_result.scalar_one_or_none()
        
        if us_unit:
            return us_unit
        
        # Try USM table
        usm_query = select(UnitaStratigraficaMuraria).where(
            and_(
                UnitaStratigraficaMuraria.site_id == site_id,
                UnitaStratigraficaMuraria.id == temp_id,
                UnitaStratigraficaMuraria.deleted_at.is_(None)
            )
        )
        usm_result = await db.execute(usm_query)
        usm_unit = usm_result.scalar_one_or_none()
        
        return usm_unit
        
    except Exception as e:
        logger.error(f"Error fetching unit by temp_id {temp_id}: {str(e)}")
        return None
# ===== COMPREHENSIVE VALIDATION AND ERROR HANDLING FIX #2 =====

async def harris_matrix_error_handler(func):
    """Decorator for comprehensive error handling"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            logger.error(f"[VALIDATION ERROR] {str(e)}")
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "validation_failed",
                    "message": str(e),
                    "validation_errors": [HarrisMatrixValidationError(
                        error_type="validation_error",
                        field="request",
                        message=str(e),
                        severity="error"
                    ).dict()]
                }
            )
        except Exception as e:
            logger.error(f"[HARRIS MATRIX ERROR] Unexpected error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_server_error",
                    "message": "An unexpected error occurred while processing the Harris Matrix",
                    "suggestions": [
                        "Check your input data for invalid relationships",
                        "Ensure all units have unique codes",
                        "Try saving a smaller subset of changes"
                    ]
                }
            )
    return wrapper