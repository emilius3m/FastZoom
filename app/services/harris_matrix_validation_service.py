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
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.stratigraphy import UnitStratigrafica, RelazioneStratigrafica
from app.models.harris_matrix_mapping import HarrisMatrixUnit, HarrisMatrixEdge
from app.exceptions.harris_matrix import (
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    CycleDetectionError,
    ValidationTimeoutError
)

logger = logging.getLogger(__name__)


class HarrisMatrixValidationService:
    """Service for validating Harris Matrix operations to prevent data corruption."""
    
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
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
            
            # Check for duplicates in database (both UnitStratigrafica and HarrisMatrixUnit)
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
        """Check for existing units in both UnitStratigrafica and HarrisMatrixUnit tables."""
        existing_units = {}
        
        # Check UnitStratigrafica table
        strat_units_query = select(UnitStratigrafica).where(
            and_(
                UnitStratigrafica.id_sito == site_id,
                UnitStratigrafica.us_code.in_(codes)
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
        strat_query = select(UnitStratigrafica).where(
            and_(
                UnitStratigrafica.id_sito == site_id,
                UnitStratigrafica.us_code == code
            )
        )
        strat_result = await db_session.execute(strat_query)
        if strat_result.scalar_one_or_none():
            return True
        
        # Check HarrisMatrixUnit
        harris_query = select(HarrisMatrixUnit).where(
            and_(
                HarrisMatrixUnit.site_id == site_id,
                HarrisMatrixUnit.unit_code == code
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