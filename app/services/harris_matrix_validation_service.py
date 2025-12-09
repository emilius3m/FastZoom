"""
Harris Matrix validation service for detecting duplicates and ensuring data integrity.

This service provides comprehensive validation for Harris Matrix operations including:
- Duplicate unit code detection
- Relationship integrity validation
- Cycle detection in stratigraphic relationships
- Performance-optimized bulk operations
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from uuid import UUID
from collections import defaultdict, deque
import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.models.stratigraphy import UnitaStratigrafica
from app.schemas.harris_matrix_editor import HarrisMatrixEdge
from app.exceptions.harris_matrix import (
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    CycleDetectionError,
    ValidationTimeoutError,
    StaleReferenceError
)

logger = logging.getLogger(__name__)


class HarrisMatrixValidationService:
    """Service for validating Harris Matrix operations to prevent data corruption."""
    
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds
    
    async def validate_duplicate_unit_codes(
        self, 
        site_id: UUID, 
        units_data: List[Dict], 
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Check for duplicate unit codes before bulk creation.
        
        Args:
            site_id: Site identifier
            units_data: List of unit data dictionaries containing 'us_code' and 'tempid'
            db_session: Database session
            
        Returns:
            {
                "is_valid": bool,
                "duplicates": List[str],  # Duplicate codes found
                "conflicts": Dict[str, Dict],  # Existing unit details
                "can_proceed": bool,
                "suggestions": List[str],
                "validation_time": float
            }
        """
        start_time = datetime.now()
        
        try:
            # Extract unit codes from input data
            input_codes = {unit.get("us_code", "").strip() for unit in units_data if unit.get("us_code")}
            if not input_codes:
                return {
                    "is_valid": True,
                    "duplicates": [],
                    "conflicts": {},
                    "can_proceed": True,
                    "suggestions": [],
                    "validation_time": 0.0
                }
            
            # Check for duplicates within the input data itself
            input_code_counts = defaultdict(int)
            for unit in units_data:
                code = unit.get("us_code", "").strip()
                if code:
                    input_code_counts[code] += 1
            
            input_duplicates = [code for code, count in input_code_counts.items() if count > 1]
            
            if input_duplicates:
                logger.warning(f"Duplicate codes in input data: {input_duplicates}")
                suggestions = []
                for code in input_duplicates:
                    suggestions.append(f"Remove duplicate occurrences of '{code}'")
                
                return {
                    "is_valid": False,
                    "duplicates": input_duplicates,
                    "conflicts": {},
                    "can_proceed": False,
                    "suggestions": suggestions,
                    "validation_time": (datetime.now() - start_time).total_seconds()
                }
            
            # Check for duplicates in database (both UnitStratigrafica and HarrisMatrixMapping)
            existing_units = await self._check_existing_units_bulk(
                site_id=site_id,
                codes=input_codes,
                db_session=db_session
            )
            
            if existing_units:
                conflicts = {}
                for code, unit_info in existing_units.items():
                    conflicts[code] = {
                        "id": str(unit_info["id"]),
                        "unit_type": unit_info["type"],
                        "description": unit_info.get("description", ""),
                        "created_at": unit_info.get("created_at"),
                        "suggestion": f"Use a different code for '{code}' or modify the existing unit"
                    }
                
                suggestions = [
                    f"Remove or rename duplicate codes: {', '.join(existing_units.keys())}",
                    "Consider using unit codes with prefixes (e.g., US1001, US1002)",
                    "Verify that the unit codes are correct for this site"
                ]
                
                logger.warning(f"Duplicate unit codes detected in database: {list(existing_units.keys())}")
                
                return {
                    "is_valid": False,
                    "duplicates": list(existing_units.keys()),
                    "conflicts": conflicts,
                    "can_proceed": False,
                    "suggestions": suggestions,
                    "validation_time": (datetime.now() - start_time).total_seconds()
                }
            
            # No duplicates found
            return {
                "is_valid": True,
                "duplicates": [],
                "conflicts": {},
                "can_proceed": True,
                "suggestions": [],
                "validation_time": (datetime.now() - start_time).total_seconds()
            }
            
        except asyncio.TimeoutError:
            raise ValidationTimeoutError(
                message="Duplicate validation timed out",
                operation="validate_duplicate_unit_codes",
                timeout_seconds=self.timeout_seconds,
                items_processed=len(units_data),
                total_items=len(units_data)
            )
        except Exception as e:
            logger.error(f"Error during duplicate validation: {str(e)}", exc_info=True)
            raise
    
    async def _check_existing_units_bulk(
        self, 
        site_id: UUID, 
        codes: Set[str], 
        db_session: AsyncSession
    ) -> Dict[str, Dict]:
        """Check for existing units in both UnitStratigrafica and HarrisMatrixMapping tables."""
        existing_units = {}
        
        # Check UnitStratigrafica table
        strat_units_query = select(UnitaStratigrafica).where(
            and_(
                UnitaStratigrafica.site_id == site_id,
                UnitaStratigrafica.us_code.in_(codes)
            )
        )
        
        strat_result = await db_session.execute(strat_units_query)
        strat_units = strat_result.scalars().all()
        
        for unit in strat_units:
            existing_units[unit.us_code] = {
                "id": unit.id,
                "type": "UnitStratigrafica",
                "description": getattr(unit, 'descrizione', ''),
                "created_at": getattr(unit, 'created_at', None)
            }
        
        # Check HarrisMatrixUnit table
        harris_units_query = select(HarrisMatrixUnit).where(
            and_(
                HarrisMatrixUnit.site_id == site_id,
                HarrisMatrixUnit.unit_code.in_(codes)
            )
        )
        
        harris_result = await db_session.execute(harris_units_query)
        harris_units = harris_result.scalars().all()
        
        for unit in harris_units:
            existing_units[unit.unit_code] = {
                "id": unit.id,
                "type": "HarrisMatrixUnit",
                "description": unit.description or '',
                "created_at": unit.created_at
            }
        
        return existing_units
    
    async def validate_relationship_integrity(
        self,
        site_id: UUID,
        relationships_data: List[Dict],
        units_mapping: Dict[str, str],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Validate that all referenced units exist in relationships.
        
        Args:
            site_id: Site identifier
            relationships_data: List of relationship dictionaries
            units_mapping: Mapping of unit codes to temp IDs
            db_session: Database session
            
        Returns:
            {
                "is_valid": bool,
                "missing_units": List[str],
                "invalid_relations": List[Dict],
                "can_proceed": bool,
                "suggestions": List[str]
            }
        """
        start_time = datetime.now()
        
        try:
            # Collect all referenced unit codes
            referenced_codes = set()
            
            for rel in relationships_data:
                from_code = rel.get("from_unit_code", "").strip()
                to_code = rel.get("to_unit_code", "").strip()
                
                if from_code:
                    referenced_codes.add(from_code)
                if to_code:
                    referenced_codes.add(to_code)
            
            if not referenced_codes:
                return {
                    "is_valid": True,
                    "missing_units": [],
                    "invalid_relations": [],
                    "can_proceed": True,
                    "suggestions": []
                }
            
            # Check which codes are missing
            missing_codes = set()
            invalid_relations = []
            
            for code in referenced_codes:
                if code not in units_mapping:
                    # Check if the unit exists in the database
                    existing_unit = await self._check_single_unit_exists(
                        site_id=site_id,
                        code=code,
                        db_session=db_session
                    )
                    
                    if not existing_unit:
                        missing_codes.add(code)
            
            # Find specific invalid relations
            for i, rel in enumerate(relationships_data):
                from_code = rel.get("from_unit_code", "").strip()
                to_code = rel.get("to_unit_code", "").strip()
                
                relation_issues = []
                
                if from_code and from_code in missing_codes:
                    relation_issues.append(f"Missing 'from_unit': {from_code}")
                
                if to_code and to_code in missing_codes:
                    relation_issues.append(f"Missing 'to_unit': {to_code}")
                
                if from_code == to_code and from_code:
                    relation_issues.append("Self-referencing relationship")
                
                if relation_issues:
                    invalid_relations.append({
                        "index": i,
                        "relationship": rel,
                        "issues": relation_issues
                    })
            
            can_proceed = len(missing_codes) == 0 and len(invalid_relations) == 0
            
            suggestions = []
            if missing_codes:
                suggestions.extend([
                    f"Create missing units first: {', '.join(sorted(missing_codes))}",
                    f"Remove references to non-existent units: {', '.join(sorted(missing_codes))}",
                    "Verify unit codes are spelled correctly"
                ])
            
            if invalid_relations:
                suggestions.append("Remove self-referencing relationships")
            
            return {
                "is_valid": can_proceed,
                "missing_units": list(sorted(missing_codes)),
                "invalid_relations": invalid_relations,
                "can_proceed": can_proceed,
                "suggestions": suggestions,
                "validation_time": (datetime.now() - start_time).total_seconds()
            }
            
        except Exception as e:
            logger.error(f"Error during relationship validation: {str(e)}", exc_info=True)
            raise
    
    async def _check_single_unit_exists(
        self, 
        site_id: UUID, 
        code: str, 
        db_session: AsyncSession
    ) -> bool:
        """Check if a single unit exists in either table."""
        # Check UnitStratigrafica
        strat_query = select(UnitaStratigrafica).where(
            and_(
                UnitaStratigrafica.site_id == site_id,
                UnitaStratigrafica.us_code == code
            )
        )
        strat_result = await db_session.execute(strat_query)
        if strat_result.scalar_one_or_none():
            return True
        
        # Check HarrisMatrixMapping
        harris_query = select(HarrisMatrixMapping).where(
            and_(
                HarrisMatrixMapping.site_id == site_id,
                HarrisMatrixMapping.unit_code == code
            )
        )
        harris_result = await db_session.execute(harris_query)
        if harris_result.scalar_one_or_none():
            return True
        
        return False
    
    async def detect_potential_cycles(
        self,
        relationships: List[Dict],
        units_mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Detect potential cycles in stratigraphic relationships.
        
        Args:
            relationships: List of relationship dictionaries
            units_mapping: Mapping of unit codes to temp IDs
            
        Returns:
            {
                "is_valid": bool,
                "cycle_paths": List[List[str]],
                "affected_units": List[str],
                "can_proceed": bool,
                "suggestions": List[str]
            }
        """
        start_time = datetime.now()
        
        try:
            # Build adjacency list
            graph = defaultdict(list)
            
            for rel in relationships:
                from_code = rel.get("from_unit_code", "").strip()
                to_code = rel.get("to_unit_code", "").strip()
                
                if from_code and to_code and from_code != to_code:
                    graph[from_code].append(to_code)
            
            # Detect cycles using DFS
            cycles = []
            visited = set()
            rec_stack = set()
            
            def dfs(node: str, path: List[str]) -> bool:
                if node in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(node)
                    cycle_path = path[cycle_start:] + [node]
                    cycles.append(cycle_path)
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
            
            # Check each node for cycles
            all_nodes = set(graph.keys()) | {neighbor for neighbors in graph.values() for neighbor in neighbors}
            
            for node in all_nodes:
                if node not in visited:
                    dfs(node, [])
            
            # Prepare results
            can_proceed = len(cycles) == 0
            affected_units = list({node for cycle in cycles for node in cycle})
            
            suggestions = []
            if cycles:
                suggestions.extend([
                    "Review and remove cyclical relationships",
                    "Verify that 'earlier than' relationships are correct",
                    "Consider using 'equivalent to' relationships for units that represent the same context"
                ])
            
            return {
                "is_valid": can_proceed,
                "cycle_paths": cycles,
                "affected_units": affected_units,
                "can_proceed": can_proceed,
                "suggestions": suggestions,
                "validation_time": (datetime.now() - start_time).total_seconds()
            }
            
        except Exception as e:
            logger.error(f"Error during cycle detection: {str(e)}", exc_info=True)
            raise
    
    async def validate_bulk_operation(
        self,
        site_id: UUID,
        units_data: List[Dict],
        relationships_data: List[Dict],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Comprehensive validation for bulk operations.
        
        Returns combined validation results with overall status.
        """
        validation_results = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "can_proceed": True,
            "validation_time": 0.0
        }
        
        start_time = datetime.now()
        
        try:
            # Step 1: Validate duplicate unit codes
            duplicate_validation = await self.validate_duplicate_unit_codes(
                site_id=site_id,
                units_data=units_data,
                db_session=db_session
            )
            
            if not duplicate_validation["can_proceed"]:
                validation_results["is_valid"] = False
                validation_results["can_proceed"] = False
                validation_results["errors"].append({
                    "type": "duplicate_codes",
                    "message": "Duplicate unit codes detected",
                    "details": duplicate_validation
                })
                validation_results["suggestions"].extend(duplicate_validation["suggestions"])
            
            # Step 2: Validate relationship integrity (only if no duplicates)
            if duplicate_validation["can_proceed"] and relationships_data:
                units_mapping = {unit["us_code"]: unit["tempid"] for unit in units_data if unit.get("us_code")}
                
                relation_validation = await self.validate_relationship_integrity(
                    site_id=site_id,
                    relationships_data=relationships_data,
                    units_mapping=units_mapping,
                    db_session=db_session
                )
                
                if not relation_validation["can_proceed"]:
                    validation_results["is_valid"] = False
                    validation_results["can_proceed"] = False
                    validation_results["errors"].append({
                        "type": "invalid_relations",
                        "message": "Invalid relationships detected",
                        "details": relation_validation
                    })
                    validation_results["suggestions"].extend(relation_validation["suggestions"])
            
            # Step 3: Detect cycles (only if relationships are valid)
            if validation_results["is_valid"] and relationships_data:
                cycle_validation = await self.detect_potential_cycles(
                    relationships=relationships_data,
                    units_mapping={unit["us_code"]: unit["tempid"] for unit in units_data if unit.get("us_code")}
                )
                
                if not cycle_validation["can_proceed"]:
                    validation_results["is_valid"] = False
                    validation_results["can_proceed"] = False
                    validation_results["errors"].append({
                        "type": "cycles_detected",
                        "message": "Cycles detected in relationships",
                        "details": cycle_validation
                    })
                    validation_results["suggestions"].extend(cycle_validation["suggestions"])
                elif cycle_validation["cycle_paths"]:
                    # Warning for potential issues
                    validation_results["warnings"].append({
                        "type": "potential_cycles",
                        "message": "Potential issues in relationships detected",
                        "details": cycle_validation
                    })
            
            validation_results["validation_time"] = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Bulk validation completed in {validation_results['validation_time']:.2f}s - "
                       f"Valid: {validation_results['is_valid']}, Errors: {len(validation_results['errors'])}")
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error during bulk validation: {str(e)}", exc_info=True)
            raise
    
    async def validate_stale_references(
        self,
        site_id: UUID,
        updates: Dict[str, Dict],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Validate that all referenced unit IDs exist before bulk updates.
        
        Args:
            site_id: Site identifier
            updates: Dictionary mapping unit IDs to update data
            db_session: Database session
            
        Returns:
            {
                "is_valid": bool,
                "missing_ids": List[str],  # Unit IDs that don't exist
                "soft_deleted_ids": List[str],  # Soft-deleted units
                "valid_ids": List[str],  # Valid unit IDs
                "wrong_site_ids": List[str],  # Units from wrong site
                "can_proceed": bool
            }
        """
        start_time = datetime.now()
        
        try:
            if not updates:
                return {
                    "is_valid": True,
                    "missing_ids": [],
                    "soft_deleted_ids": [],
                    "valid_ids": [],
                    "wrong_site_ids": [],
                    "can_proceed": True
                }
            
            # Extract all unit IDs from updates
            unit_ids = list(updates.keys())
            
            # Normalize unit IDs (handle both UUID and hash formats)
            normalized_ids = []
            for unit_id in unit_ids:
                if len(unit_id) == 32 and '-' not in unit_id:
                    # Convert hash format to UUID format
                    normalized_id = f"{unit_id[0:8]}-{unit_id[8:12]}-{unit_id[12:16]}-{unit_id[16:20]}-{unit_id[20:]}"
                    normalized_ids.append(normalized_id)
                else:
                    normalized_ids.append(unit_id)
            
            # Bulk check for existing units with performance optimization
            existing_units_query = select(UnitaStratigrafica).where(
                UnitaStratigrafica.id.in_(normalized_ids)
            )
            existing_result = await db_session.execute(existing_units_query)
            existing_units = existing_result.scalars().all()
            
            # Build mapping of existing units
            existing_unit_map = {
                str(unit.id): {
                    "id": str(unit.id),
                    "site_id": str(unit.site_id),
                    "deleted_at": unit.deleted_at,
                    "us_code": unit.us_code
                }
                for unit in existing_units
            }
            
            # Analyze each unit ID
            missing_ids = []
            soft_deleted_ids = []
            wrong_site_ids = []
            valid_ids = []
            
            for i, original_id in enumerate(unit_ids):
                normalized_id = normalized_ids[i]
                unit_info = existing_unit_map.get(normalized_id)
                
                if not unit_info:
                    # Try with original ID (fallback for non-normalized entries)
                    unit_info = existing_unit_map.get(original_id)
                
                if not unit_info:
                    missing_ids.append(original_id)
                    continue
                
                if unit_info["deleted_at"] is not None:
                    soft_deleted_ids.append(original_id)
                    continue
                
                if unit_info["site_id"] != str(site_id):
                    wrong_site_ids.append(original_id)
                    continue
                
                valid_ids.append(original_id)
            
            can_proceed = len(missing_ids) == 0 and len(soft_deleted_ids) == 0 and len(wrong_site_ids) == 0
            
            logger.info(f"Stale reference validation completed - "
                       f"Total: {len(unit_ids)}, Valid: {len(valid_ids)}, "
                       f"Missing: {len(missing_ids)}, Soft-deleted: {len(soft_deleted_ids)}, "
                       f"Wrong site: {len(wrong_site_ids)}")
            
            return {
                "is_valid": can_proceed,
                "missing_ids": missing_ids,
                "soft_deleted_ids": soft_deleted_ids,
                "valid_ids": valid_ids,
                "wrong_site_ids": wrong_site_ids,
                "can_proceed": can_proceed,
                "validation_time": (datetime.now() - start_time).total_seconds()
            }
            
        except asyncio.TimeoutError:
            raise ValidationTimeoutError(
                message="Stale reference validation timed out",
                operation="validate_stale_references",
                timeout_seconds=self.timeout_seconds,
                items_processed=len(updates),
                total_items=len(updates)
            )
        except Exception as e:
            logger.error(f"Error during stale reference validation: {str(e)}", exc_info=True)
            raise
    
    async def validate_bulk_update_integrity(
        self,
        site_id: UUID,
        updates: Dict[str, Dict],
        db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Comprehensive validation for bulk update operations.
        
        Validates:
        - Unit existence
        - Permission to update (not soft-deleted)
        - Site ownership
        - Data format validity
        - Relationship integrity
        
        Args:
            site_id: Site identifier
            updates: Dictionary mapping unit IDs to update data
            db_session: Database session
            
        Returns:
            {
                "is_valid": bool,
                "missing_ids": List[str],
                "soft_deleted_ids": List[str],
                "wrong_site_ids": List[str],
                "invalid_data": List[Dict],  # Units with invalid update data
                "relationship_issues": List[Dict],  # Issues in sequenza_fisica relationships
                "can_proceed": bool,
                "suggestions": List[str],
                "validation_details": Dict[str, Any]
            }
        """
        start_time = datetime.now()
        
        try:
            if not updates:
                return {
                    "is_valid": True,
                    "missing_ids": [],
                    "soft_deleted_ids": [],
                    "wrong_site_ids": [],
                    "invalid_data": [],
                    "relationship_issues": [],
                    "can_proceed": True,
                    "suggestions": [],
                    "validation_details": {"validation_time": 0.0}
                }
            
            # Step 1: Validate stale references
            stale_validation = await self.validate_stale_references(
                site_id=site_id,
                updates=updates,
                db_session=db_session
            )
            
            # Step 2: Validate data format for valid units
            invalid_data = []
            valid_unit_ids = stale_validation["valid_ids"]
            
            # Batch get valid units for detailed validation
            if valid_unit_ids:
                # Normalize valid IDs for query
                normalized_valid_ids = []
                for unit_id in valid_unit_ids:
                    if len(unit_id) == 32 and '-' not in unit_id:
                        normalized_id = f"{unit_id[0:8]}-{unit_id[8:12]}-{unit_id[12:16]}-{unit_id[16:20]}-{unit_id[20:]}"
                        normalized_valid_ids.append(normalized_id)
                    else:
                        normalized_valid_ids.append(unit_id)
                
                valid_units_query = select(UnitaStratigrafica).where(
                    UnitaStratigrafica.id.in_(normalized_valid_ids)
                )
                valid_result = await db_session.execute(valid_units_query)
                valid_units = valid_result.scalars().all()
                
                valid_units_map = {str(unit.id): unit for unit in valid_units}
                
                for unit_id in valid_unit_ids:
                    update_data = updates[unit_id]
                    unit = valid_units_map.get(unit_id) or valid_units_map.get(
                        f"{unit_id[0:8]}-{unit_id[8:12]}-{unit_id[12:16]}-{unit_id[16:20]}-{unit_id[20:]}"
                        if len(unit_id) == 32 and '-' not in unit_id else unit_id
                    )
                    
                    if not unit:
                        # This shouldn't happen if stale validation passed, but safety check
                        invalid_data.append({
                            "unit_id": unit_id,
                            "reason": "unit_not_found_in_db",
                            "suggestion": "Refresh the page and try again"
                        })
                        continue
                    
                    # Validate sequenza_fisica format
                    sequenza_fisica = update_data.get('sequenza_fisica')
                    if sequenza_fisica is not None:
                        if not isinstance(sequenza_fisica, dict):
                            invalid_data.append({
                                "unit_id": unit_id,
                                "reason": "invalid_sequenza_format",
                                "suggestion": "sequenza_fisica must be a dictionary"
                            })
                        else:
                            # Validate structure of sequenza_fisica
                            required_keys = [
                                "uguale_a", "si_lega_a", "gli_si_appoggia", "si_appoggia_a",
                                "coperto_da", "copre", "tagliato_da", "taglia", "riempito_da", "riempie"
                            ]
                            
                            for key in required_keys:
                                if key not in sequenza_fisica:
                                    invalid_data.append({
                                        "unit_id": unit_id,
                                        "reason": f"missing_sequenza_key_{key}",
                                        "suggestion": f"Add '{key}' array to sequenza_fisica"
                                    })
                                elif not isinstance(sequenza_fisica[key], list):
                                    invalid_data.append({
                                        "unit_id": unit_id,
                                        "reason": f"invalid_sequenza_key_type_{key}",
                                        "suggestion": f"'{key}' must be a list"
                                    })
            
            # Step 3: Check for relationship integrity issues
            relationship_issues = []
            for unit_id in valid_unit_ids:
                update_data = updates[unit_id]
                sequenza_fisica = update_data.get('sequenza_fisica', {})
                
                if isinstance(sequenza_fisica, dict):
                    # Collect all referenced unit codes
                    referenced_codes = set()
                    for relation_type, target_codes in sequenza_fisica.items():
                        if isinstance(target_codes, list):
                            referenced_codes.update(target_codes)
                    
                    # Validate each referenced code exists
                    for code in referenced_codes:
                        if code:  # Skip empty strings
                            # Check if code exists as a US in the site
                            code_exists = await self._check_unit_code_exists(
                                site_id=site_id,
                                code=code,
                                db_session=db_session
                            )
                            
                            if not code_exists:
                                relationship_issues.append({
                                    "unit_id": unit_id,
                                    "referenced_code": code,
                                    "relation_type": "unknown",
                                    "reason": "referenced_unit_not_found",
                                    "suggestion": f"Verify unit code '{code}' exists or remove reference"
                                })
            
            # Step 4: Generate suggestions
            suggestions = []
            
            if stale_validation["missing_ids"]:
                suggestions.extend([
                    f"Remove references to missing units: {', '.join(stale_validation['missing_ids'])}",
                    "Verify unit IDs are correct and haven't been deleted"
                ])
            
            if stale_validation["soft_deleted_ids"]:
                suggestions.extend([
                    f"Restore soft-deleted units: {', '.join(stale_validation['soft_deleted_ids'])}",
                    "Or remove references to soft-deleted units"
                ])
            
            if stale_validation["wrong_site_ids"]:
                suggestions.append(
                    f"Units belong to different site: {', '.join(stale_validation['wrong_site_ids'])}"
                )
            
            if invalid_data:
                suggestions.append("Fix invalid data format in sequenza_fisica updates")
            
            if relationship_issues:
                suggestions.append("Fix references to non-existent unit codes")
            
            # Final validation result
            can_proceed = (
                len(stale_validation["missing_ids"]) == 0 and
                len(stale_validation["soft_deleted_ids"]) == 0 and
                len(stale_validation["wrong_site_ids"]) == 0 and
                len(invalid_data) == 0 and
                len(relationship_issues) == 0
            )
            
            validation_details = {
                "stale_reference_validation": stale_validation,
                "data_validation": {
                    "invalid_data_count": len(invalid_data),
                    "invalid_data": invalid_data
                },
                "relationship_validation": {
                    "relationship_issues_count": len(relationship_issues),
                    "relationship_issues": relationship_issues
                }
            }
            
            logger.info(f"Bulk update integrity validation completed - "
                       f"Can proceed: {can_proceed}, "
                       f"Invalid data: {len(invalid_data)}, "
                       f"Relationship issues: {len(relationship_issues)}")
            
            return {
                "is_valid": can_proceed,
                "missing_ids": stale_validation["missing_ids"],
                "soft_deleted_ids": stale_validation["soft_deleted_ids"],
                "wrong_site_ids": stale_validation["wrong_site_ids"],
                "invalid_data": invalid_data,
                "relationship_issues": relationship_issues,
                "can_proceed": can_proceed,
                "suggestions": suggestions,
                "validation_details": validation_details,
                "validation_time": (datetime.now() - start_time).total_seconds()
            }
            
        except asyncio.TimeoutError:
            raise ValidationTimeoutError(
                message="Bulk update integrity validation timed out",
                operation="validate_bulk_update_integrity",
                timeout_seconds=self.timeout_seconds,
                items_processed=len(updates),
                total_items=len(updates)
            )
        except Exception as e:
            logger.error(f"Error during bulk update integrity validation: {str(e)}", exc_info=True)
            raise
    
    async def _check_unit_code_exists(
        self,
        site_id: UUID,
        code: str,
        db_session: AsyncSession
    ) -> bool:
        """Check if a unit with the given code exists in the site."""
        try:
            query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.us_code == code,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            result = await db_session.execute(query)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Error checking unit code existence: {str(e)}", exc_info=True)
            return False