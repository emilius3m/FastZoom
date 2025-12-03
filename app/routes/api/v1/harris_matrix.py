# app/routes/api/v1/harris_matrix.py - Harris Matrix API v1 endpoints

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any, Optional, List
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.services.harris_matrix_service import HarrisMatrixService
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
    HarrisMatrixBulkCreateRelationship
)
from app.exceptions import (
    HarrisMatrixValidationError,
    StratigraphicCycleDetected,
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    HarrisMatrixServiceError,
    BusinessLogicError
)
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from sqlalchemy import select, and_, or_

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
        
        # Rule: Only negative US can cut (taglia/tagliato_da)
        if rel_type in ['taglia', 'tagliato_da']:
            if from_unit.unit_type == 'us' and from_unit.tipo != 'negativa':
                errors.append(
                    f"Unit {from_unit.temp_id} ({from_unit.tipo}) cannot {rel_type}. "
                    f"Only negative US units can cut other units"
                )
                field_errors[f"relationships.{rel.temp_id}"] = "Business rule violation"
                suggestions.append("Change US type to 'negativa' or use different relationship")
        
        # Rule: Positive US can cover/fill (copre/riempie)
        if rel_type in ['copre', 'riempie']:
            if from_unit.unit_type == 'us' and from_unit.tipo != 'positiva':
                errors.append(
                    f"Unit {from_unit.temp_id} ({from_unit.tipo}) cannot {rel_type}. "
                    f"Only positive US units can cover or fill other units"
                )
                field_errors[f"relationships.{rel.temp_id}"] = "Business rule violation"
                suggestions.append("Change US type to 'positiva' or use different relationship")
        
        # Rule: USM units should not have tipo field
        if from_unit.unit_type == 'usm' and from_unit.tipo:
            errors.append(f"USM unit {from_unit.temp_id} should not have tipo field")
            field_errors[f"units.{from_unit.temp_id}.tipo"] = "Field not applicable"
    
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
    
    This is a simplified cycle detection for the request data.
    More comprehensive cycle detection happens in the service layer.
    """
    try:
        # Build graph from relationships
        graph = {}
        unit_temp_ids = {unit.temp_id for unit in units}
        
        # Initialize graph
        for temp_id in unit_temp_ids:
            graph[temp_id] = []
        
        # Add directed relationships
        directed_relationships = ['copre', 'taglia', 'si_appoggia_a', 'riempie']
        
        for rel in relationships:
            if rel.relation_type.value in directed_relationships:
                from_temp = rel.from_temp_id
                to_temp = rel.to_temp_id
                if from_temp in graph and to_temp in unit_temp_ids:
                    graph[from_temp].append(to_temp)
        
        # DFS cycle detection
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node: str, path: List[str]) -> bool:
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return True
            
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                if dfs(neighbor, path.copy()):
                    return True
            
            rec_stack.remove(node)
            return False
        
        for temp_id in unit_temp_ids:
            if temp_id not in visited:
                dfs(temp_id, [])
        
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
        units_data = [
            {
                **unit.dict(exclude_none=True),
                'created_by': user_sites[0].get('user_id') if user_sites else None
            }
            for unit in request.units
        ]
        
        relationships_data = [rel.dict() for rel in request.relationships]
        
        # Perform bulk creation with pre-validated data
        result = await harris_service.bulk_create_units_with_relationships(
            site_id=site_id,
            units_data=units_data,
            relationships_data=relationships_data
        )
        
        # Convert result to response schema
        response = HarrisMatrixBulkCreateResponse(
            success=True,
            message=f"Successfully created {result['created_units']} units and {result['created_relationships']} relationships",
            site_id=site_id,
            created_units=result['created_units'],
            created_relationships=result['created_relationships'],
            unit_mapping=result['unit_mapping'],
            relationship_mapping=result['relationship_mapping'],
            units=result['units'],
            relationships=result['relationships'],
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
        
        # Initialize service and perform bulk update
        harris_service = HarrisMatrixService(db)
        result = await harris_service.bulk_update_relationships(
            site_id=site_id,
            unit_id=request.unit_id,
            unit_type=request.unit_type.value,
            relationships_update=relationships_update
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
        
        # Get source unit
        if request.from_unit_type == UnitTypeEnum.US:
            from_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.us_code == request.from_unit_code,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            from_result = await db.execute(from_query)
            from_unit = from_result.scalar_one_or_none()
        else:  # USM
            from_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.usm_code == request.from_unit_code,
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            from_result = await db.execute(from_query)
            from_unit = from_result.scalar_one_or_none()
        
        # Get target unit
        if request.to_unit_type == UnitTypeEnum.US:
            to_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.us_code == request.to_unit_code,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            to_result = await db.execute(to_query)
            to_unit = to_result.scalar_one_or_none()
        else:  # USM
            to_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.usm_code == request.to_unit_code,
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            to_result = await db.execute(to_query)
            to_unit = to_result.scalar_one_or_none()
        
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
        
        # Validate the relationship
        await harris_service._validate_single_relationship(
            from_unit, to_unit, request.relation_type.value
        )
        
        # Additional business rule validation
        errors = []
        warnings = []
        
        # Check self-relationship
        if from_unit.id == to_unit.id:
            errors.append("Unit cannot have relationship with itself")
        
        # Check US type rules
        if hasattr(from_unit, 'tipo') and request.relation_type in [StratigraphicRelation.TAGLIA, StratigraphicRelation.TAGLIATO_DA]:
            if from_unit.tipo != 'negativa':
                errors.append("Only negative US units can cut other units")
        
        if hasattr(from_unit, 'tipo') and request.relation_type in [StratigraphicRelation.COPRE, StratigraphicRelation.RIEMPIE]:
            if from_unit.tipo != 'positiva':
                errors.append("Only positive US units can cover or fill other units")
        
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
        
        if request.unit_type == UnitTypeEnum.US:
            existing_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.us_code == request.code,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            existing_result = await db.execute(existing_query)
            existing_unit = existing_result.scalar_one_or_none()
        else:  # USM
            existing_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.usm_code == request.code,
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            existing_result = await db.execute(existing_query)
            existing_unit = existing_result.scalar_one_or_none()
        
        if existing_unit:
            errors.append(f"Unit code {request.code} is already in use")
        
        # Check for similar codes that might cause confusion
        similar_query = None
        if request.unit_type == UnitTypeEnum.US:
            similar_query = select(UnitaStratigrafica.us_code).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.us_code.ilike(f"%{request.code[2:]}%"),
                    UnitaStratigrafica.deleted_at.is_(None),
                    UnitaStratigrafica.us_code != request.code
                )
            )
        else:  # USM
            similar_query = select(UnitaStratigraficaMuraria.usm_code).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.usm_code.ilike(f"%{request.code[3:]}%"),
                    UnitaStratigraficaMuraria.deleted_at.is_(None),
                    UnitaStratigraficaMuraria.usm_code != request.code
                )
            )
        
        if similar_query:
            similar_result = await db.execute(similar_query)
            similar_codes = similar_result.scalars().all()
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