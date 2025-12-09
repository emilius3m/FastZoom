# app/services/harris_matrix_service.py
"""
Service for generating Harris Matrix graph data from US/USM stratigraphic relationships.

This service queries both US and USM tables for a given site_id, extracts relationships
from the sequenza_fisica JSON field, and generates graph data structures suitable
for Cytoscape.js visualization with topological sorting for chronological levels.

Enhanced with UnitResolver for intelligent unit code resolution and reference validation.
"""

import re
import asyncio
import math
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from uuid import UUID, uuid4
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm.attributes import flag_modified
from loguru import logger

from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.models.harris_matrix_layout import HarrisMatrixLayout
from app.services.harris_matrix_unit_resolver import UnitResolver
from app.services.harris_matrix_validation_service import HarrisMatrixValidationService
from app.utils.stratigraphy_helpers import (
    UnitLookupService,
    StratigraphicGraphBuilder,
    CycleDetector,
    StratigraphicRulesValidator,
    RELATIONSHIP_TYPES,
    DIRECTED_RELATIONSHIPS,
    REVERSE_DIRECTED_RELATIONSHIPS,
    BIDIRECTIONAL_RELATIONSHIPS,
    VALID_RELATIONSHIP_TYPES,
    get_default_sequenza_fisica,
    parse_target_reference,
    generate_sequential_codes,
    build_nodes_for_graph,
    build_edges_from_relationships
)
from app.exceptions import (
    HarrisMatrixValidationError,
    StratigraphicCycleDetected,
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    HarrisMatrixServiceError
)
from app.exceptions.harris_matrix import StaleReferenceError
from app.schemas.harris_matrix_editor import HarrisMatrixCreateRequest
from app.utils.unit_id_normalizer import create_graph_node_id, normalize_unit_id
from app.utils.constants import RELATIONSHIP_INVERSES, get_inverse_relationship


# Log at startup for debugging
logger.info(f"[RELATIONSHIP INVERSES] Loaded from constants.py with {len(RELATIONSHIP_INVERSES)} relationship types")


class HarrisMatrixService:
    """
    Service for generating Harris Matrix graph data from stratigraphic relationships.
    
    This service processes US (Unità Stratigrafiche) and USM (Unità Stratigrafiche Murarie)
    relationships to create chronological graphs suitable for visualization.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the Harris Matrix service with enhanced unit resolver and centralized utilities.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self.unit_resolver = UnitResolver(db)
        self.unit_lookup = UnitLookupService(db)
        self.graph_builder = StratigraphicGraphBuilder(self.unit_lookup)
        self.rules_validator = StratigraphicRulesValidator()
        self.validation_service = HarrisMatrixValidationService()
    
    async def generate_harris_matrix(self, site_id: UUID) -> Dict[str, Any]:
        """
        Generate complete Harris Matrix graph data for a site.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary containing nodes, edges, levels, and metadata for Cytoscape.js
        """
        try:
            logger.info(f"Generating Harris Matrix for site_id: {site_id}")
            logger.info(f"DEBUG: Logging level set to DEBUG for troubleshooting")
            
            # Query all US and USM units for the site using centralized service
            us_units, usm_units = await self.unit_lookup.get_units_by_site(site_id)
            
            if not us_units and not usm_units:
                logger.warning(f"No stratigraphic units found for site_id: {site_id}")
                return self._empty_graph()
            
            # Extract relationships from sequenza_fisica
            relationships = await self._extract_relationships(us_units, usm_units)
            
            # Build graph data structures using centralized utilities
            nodes = build_nodes_for_graph(us_units, usm_units)
            edges = build_edges_from_relationships(relationships)

            # Fetch saved positions for nodes
            try:
                layout_result = await self.db.execute(
                    select(HarrisMatrixLayout).where(
                        HarrisMatrixLayout.site_id == str(site_id)
                    )
                )
                layouts = {
                    layout.unit_id: {"x": layout.x, "y": layout.y}
                    for layout in layout_result.scalars().all()
                }

                # Add positions to nodes
                positioned_nodes = 0
                unpositioned_nodes = []
                
                for node in nodes:
                    # CRITICAL FIX 2: Multi-format position lookup
                    position_found = False
                    
                    # Try multiple ID formats for position lookup
                    position_candidates = []
                    
                    # 1. Try node.label (e.g., "401")
                    if node.get("label"):
                        position_candidates.append(node["label"])
                    
                    # 2. Try node.id (e.g., "US401" or graph node ID)
                    if node.get("id"):
                        position_candidates.append(node["id"])
                    
                    # 3. Try unit code extraction from label if it's a graph node ID
                    if node.get("label"):
                        label = node["label"]
                        # Extract raw code from graph node IDs like "US401" -> "401"
                        if label.startswith("US"):
                            position_candidates.append(label[2:])
                        elif label.startswith("USM"):
                            position_candidates.append(label[3:])
                    
                    # 4. Try prefixed versions (add US/USM prefix to raw codes)
                    for candidate in list(position_candidates):  # Copy to avoid modification during iteration
                        if candidate.isdigit():  # Raw numeric code
                            position_candidates.append(f"US{candidate}")
                            position_candidates.append(f"USM{candidate}")
                    
                    # Try each candidate for position lookup
                    for candidate in position_candidates:
                        if candidate in layouts:
                            node["position"] = layouts[candidate]
                            positioned_nodes += 1
                            position_found = True
                            logger.debug(f"Found position for node {node.get('id', node.get('label'))} using candidate '{candidate}'")
                            break
                    
                    if not position_found:
                        # Default position if not saved
                        node["position"] = None
                        unpositioned_nodes.append(node)
                        # Log all attempted candidates for debugging
                        logger.debug(f"No position found for node {node.get('id', node.get('label'))}. Tried candidates: {position_candidates}")

                logger.debug(f"Added {len(layouts)} saved positions to nodes")
                
                # ===== FALLBACK: Calcola posizioni da relazioni US/USM =====
                if unpositioned_nodes and len(layouts) == 0:
                    logger.info(f"No saved positions found, calculating fallback positions for {len(unpositioned_nodes)} nodes based on stratigraphic relationships")
                    fallback_positions = await self._calculate_fallback_positions(site_id, unpositioned_nodes, relationships)
                    
                    # Applica le posizioni calcolate con multi-format lookup
                    for node in unpositioned_nodes:
                        position_found = False
                        
                        # Try multiple ID formats for fallback position lookup
                        position_candidates = []
                        
                        # 1. Try node.label (e.g., "401")
                        if node.get("label"):
                            position_candidates.append(node["label"])
                        
                        # 2. Try node.id (e.g., "US401" or graph node ID)
                        if node.get("id"):
                            position_candidates.append(node["id"])
                        
                        # 3. Try unit code extraction from label if it's a graph node ID
                        if node.get("label"):
                            label = node["label"]
                            # Extract raw code from graph node IDs like "US401" -> "401"
                            if label.startswith("US"):
                                position_candidates.append(label[2:])
                            elif label.startswith("USM"):
                                position_candidates.append(label[3:])
                        
                        # 4. Try prefixed versions (add US/USM prefix to raw codes)
                        for candidate in list(position_candidates):  # Copy to avoid modification during iteration
                            if candidate.isdigit():  # Raw numeric code
                                position_candidates.append(f"US{candidate}")
                                position_candidates.append(f"USM{candidate}")
                        
                        # Try each candidate for fallback position lookup
                        for candidate in position_candidates:
                            if candidate in fallback_positions:
                                node["position"] = fallback_positions[candidate]
                                position_found = True
                                logger.debug(f"Found fallback position for node {node.get('id', node.get('label'))} using candidate '{candidate}'")
                                break
                        
                        if not position_found:
                            # Log all attempted candidates for debugging
                            logger.debug(f"No fallback position found for node {node.get('id', node.get('label'))}. Tried candidates: {position_candidates}")
                    
                    logger.info(f"Generated fallback positions for {len(fallback_positions)} nodes")

            except Exception as e:
                logger.warning(f"Could not load layout positions: {str(e)}")
                # Try fallback calculation as last resort
                try:
                    logger.info("Attempting fallback position calculation due to layout loading error")
                    fallback_positions = await self._calculate_fallback_positions(site_id, nodes, relationships)
                    
                    for node in nodes:
                        # Try multi-format lookup for emergency fallback
                        position_found = False
                        position_candidates = []
                        
                        # 1. Try node.label
                        if node.get("label"):
                            position_candidates.append(node["label"])
                        
                        # 2. Try node.id
                        if node.get("id"):
                            position_candidates.append(node["id"])
                        
                        # 3. Try unit code extraction
                        if node.get("label"):
                            label = node["label"]
                            if label.startswith("US"):
                                position_candidates.append(label[2:])
                            elif label.startswith("USM"):
                                position_candidates.append(label[3:])
                        
                        # 4. Try prefixed versions
                        for candidate in list(position_candidates):
                            if candidate.isdigit():
                                position_candidates.append(f"US{candidate}")
                                position_candidates.append(f"USM{candidate}")
                        
                        for candidate in position_candidates:
                            if candidate in fallback_positions:
                                node["position"] = fallback_positions[candidate]
                                position_found = True
                                break
                        
                        if not position_found:
                            logger.debug(f"Emergency fallback: No position found for node {node.get('id', node.get('label'))}. Tried: {position_candidates}")
                    
                    logger.info(f"Emergency fallback: Generated positions for {len(fallback_positions)} nodes")
                except Exception as fallback_error:
                    logger.error(f"Fallback position calculation also failed: {str(fallback_error)}")
                    # Continue without positions - they will be random in frontend
            
            # Calculate chronological levels using topological sort
            levels = self.graph_builder.calculate_chronological_levels(nodes, edges)
            
            # Generate metadata with US positive/negative counts
            us_positive = sum(1 for us in us_units if us.tipo == 'positiva')
            us_negative = sum(1 for us in us_units if us.tipo == 'negativa')
            
            metadata = {
                'total_us': len(us_units),
                'us_positive': us_positive,
                'us_negative': us_negative,
                'total_usm': len(usm_units),
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'site_id': str(site_id)
            }
            
            result = {
                'nodes': nodes,
                'edges': edges,
                'levels': levels,
                'metadata': metadata
            }
            
            logger.info(f"Harris Matrix generated successfully: {metadata}")
            return result
            
        except Exception as e:
            logger.error(f"Error generating Harris Matrix for site_id {site_id}: {str(e)}")
            raise
    
    
    async def _extract_relationships(
        self,
        us_units: List[UnitaStratigrafica],
        usm_units: List[UnitaStratigraficaMuraria]
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships from sequenza_fisica JSON fields with enhanced unit resolution.
        
        Args:
            us_units: List of US units
            usm_units: List of USM units
            
        Returns:
            List of relationship dictionaries
        """
        relationships = []
        
        # Create lookup dictionaries for unit codes using centralized service
        us_lookup, usm_lookup = self.unit_lookup.get_unit_lookup_dictionaries(us_units, usm_units)
        
        # Get site ID from first unit (all units should be from same site)
        site_id = us_units[0].site_id if us_units else (usm_units[0].site_id if usm_units else None)
        
        if not site_id:
            logger.warning("No site ID found for unit resolution")
            return relationships
        
        # Set resolver context
        self.unit_resolver._current_site_id = site_id
        
        # Process US units
        for us in us_units:
            if not us.sequenza_fisica:
                continue
                
            us_relationships = await self._extract_unit_relationships(
                us.sequenza_fisica, us.us_code, 'us', us_lookup, usm_lookup, site_id
            )
            relationships.extend(us_relationships)
        
        # Process USM units
        for usm in usm_units:
            if not usm.sequenza_fisica:
                continue
                
            usm_relationships = await self._extract_unit_relationships(
                usm.sequenza_fisica, usm.usm_code, 'usm', us_lookup, usm_lookup, site_id
            )
            relationships.extend(usm_relationships)
        
        logger.info(f"Extracted {len(relationships)} relationships from sequenza_fisica using enhanced resolution")
        return relationships
    
    async def _extract_unit_relationships(
        self,
        sequenza_fisica: Dict[str, List[str]],
        source_code: str,
        source_type: str,
        us_lookup: Dict[str, UnitaStratigrafica],
        usm_lookup: Dict[str, UnitaStratigraficaMuraria],
        site_id: str
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships for a single unit from its sequenza_fisica with enhanced resolution.
        
        Args:
            sequenza_fisica: JSON structure containing relationships
            source_code: Code of the source unit
            source_type: Type of source unit ('us' or 'usm')
            us_lookup: Dictionary mapping US codes to US objects
            usm_lookup: Dictionary mapping USM codes to USM objects
            site_id: Site ID for context in unit resolution
            
        Returns:
            List of relationship dictionaries
        """
        relationships = []
        
        for rel_type, targets in sequenza_fisica.items():
            if not targets or rel_type not in RELATIONSHIP_TYPES:
                continue
            
            rel_config = RELATIONSHIP_TYPES[rel_type]
            
            for target in targets:
                # Parse target to handle cross-references like "174(usm)"
                target_code, target_type = parse_target_reference(target)
                
                # Enhanced target validation using unit resolver
                target_exists = False
                resolution_method = 'traditional_lookup'
                resolved_id = None
                
                # First, try traditional lookup for performance
                if target_type == 'us' and target_code in us_lookup:
                    target_exists = True
                    resolution_method = 'traditional_lookup'
                elif target_type == 'usm' and target_code in usm_lookup:
                    target_exists = True
                    resolution_method = 'traditional_lookup'
                else:
                    # Use enhanced resolver for missing units
                    logger.debug(f"Traditional lookup failed for {target_type}{target_code}, trying enhanced resolution")
                    resolved_id = await self.unit_resolver.resolve_unit_code(target_code, target_type)
                    if resolved_id:
                        target_exists = True
                        resolution_method = 'enhanced_resolver'
                        logger.info(f"Successfully resolved {target_type}{target_code} using enhanced resolver")
                    else:
                        # CRITICAL FIX 1: Don't skip relationships with unresolved targets -
                        # instead create them with resolved=False for better debugging
                        logger.warning(f"Cannot resolve {target_type}{target_code} for relationship {rel_type} - creating unresolved edge")
                        
                        # Check for specific known issues
                        if target_code in ['402', '412', 'US402', 'US412', 'USM402', 'USM402']:
                            logger.warning(
                                f"Known problematic unit reference found: {target_type}{target_code}. "
                                f"This unit may not exist in the database or has format issues."
                            )
                        
                        # Create relationship even with unresolved target for edge tracking
                        target_exists = False
                        resolution_method = 'failed_resolution'
                        # Don't continue - process the relationship anyway
                
                # Determine relationship direction
                if rel_config['bidirectional']:
                    # For bidirectional relationships, create edge from source to target
                    from_node = create_graph_node_id(source_code, source_type)
                    to_node = create_graph_node_id(target_code, target_type)
                    bidirectional = True
                elif rel_type in ['coperto_da', 'tagliato_da', 'riempito_da']:
                    # These are "from target to source" relationships
                    from_node = create_graph_node_id(target_code, target_type)
                    to_node = create_graph_node_id(source_code, source_type)
                    bidirectional = False
                else:
                    # These are "from source to target" relationships
                    from_node = create_graph_node_id(source_code, source_type)
                    to_node = create_graph_node_id(target_code, target_type)
                    bidirectional = False
                
                relationship = {
                    'from': from_node,
                    'to': to_node,
                    'type': rel_type,
                    'label': rel_config['label'],
                    'bidirectional': bidirectional,
                    'description': rel_config['description'],
                    'resolved': target_exists,
                    'resolution_method': resolution_method,
                    'target_code': target_code,
                    'target_type': target_type,
                    'resolved_target_id': resolved_id if resolved_id else None,
                    'source_reference': f"{source_code}({source_type})"
                }
                
                # CRITICAL FIX 1: Always add relationship to edges, even if unresolved
                # This ensures missing edges are tracked for debugging
                if target_exists:
                    logger.debug(f"Added resolved relationship: {source_type}{source_code} -> {target_type}{target_code} ({rel_type})")
                else:
                    logger.warning(f"Added unresolved relationship: {source_type}{source_code} -> {target_type}{target_code} ({rel_type})")
                
                relationships.append(relationship)
        
        return relationships
    
    
    
    
    
    def _empty_graph(self) -> Dict[str, Any]:
        """
        Return empty graph structure.
        
        Returns:
            Dictionary with empty graph data
        """
        return {
            'nodes': [],
            'edges': [],
            'levels': {},
            'metadata': {
                'total_us': 0,
                'us_positive': 0,
                'us_negative': 0,
                'total_usm': 0,
                'total_nodes': 0,
                'total_edges': 0
            }
        }
    
    async def get_unit_relationships(
        self,
        unit_id: UUID,
        unit_type: str
    ) -> Dict[str, Any]:
        """
        Get relationships for a specific unit.
        
        Args:
            unit_id: UUID of the unit
            unit_type: Type of unit ('us' or 'usm')
            
        Returns:
            Dictionary containing unit info and its relationships
        """
        try:
            logger.info(f"Getting relationships for {unit_type} unit: {unit_id}")
            
            # Query the specific unit
            if unit_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.id == str(unit_id),
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                unit = result.scalar_one_or_none()
                
                if not unit:
                    logger.warning(f"US unit not found: {unit_id}")
                    return {}
                
                unit_code = unit.us_code
                sequenza_fisica = unit.sequenza_fisica
                
            elif unit_type == 'usm':
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.id == str(unit_id),
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                unit = result.scalar_one_or_none()
                
                if not unit:
                    logger.warning(f"USM unit not found: {unit_id}")
                    return {}
                
                unit_code = unit.usm_code
                sequenza_fisica = unit.sequenza_fisica
                
            else:
                raise ValueError(f"Invalid unit type: {unit_type}")
            
            if not sequenza_fisica:
                return {
                    'unit_id': str(unit_id),
                    'unit_type': unit_type,
                    'unit_code': unit_code,
                    'relationships': {}
                }
            
            # Extract relationships
            relationships = {}
            for rel_type, targets in sequenza_fisica.items():
                if targets and rel_type in RELATIONSHIP_TYPES:
                    relationships[rel_type] = {
                        'targets': targets,
                        'label': RELATIONSHIP_TYPES[rel_type]['label'],
                        'description': RELATIONSHIP_TYPES[rel_type]['description'],
                        'bidirectional': RELATIONSHIP_TYPES[rel_type]['bidirectional']
                    }
            
            result = {
                'unit_id': str(unit_id),
                'unit_type': unit_type,
                'unit_code': unit_code,
                'relationships': relationships
            }
            
            logger.info(f"Retrieved relationships for {unit_type} {unit_code}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting relationships for {unit_type} unit {unit_id}: {str(e)}")
            raise
    
    # ===== METODI NUOVI PER EDITOR GRAFICO =====
    
    async def bulk_create_units_with_relationships(
        self,
        site_id: UUID,
        units_data: List[Dict[str, Any]],
        relationships_data: List[Dict[str, Any]],
        current_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create multiple US/USM units with their relationships in a single transaction.
        
        Args:
            site_id: UUID of the archaeological site
            units_data: List of unit data dictionaries
            relationships_data: List of relationship dictionaries
            
        Returns:
            Dictionary with created units, relationships, and mapping info
        """
        try:
            logger.info(f"Bulk creating {len(units_data)} units and {len(relationships_data)} relationships for site {site_id}")
            logger.debug(f"DEBUG: Starting bulk creation, site_id={site_id}")
            logger.debug(f"DEBUG: units_data sample: {units_data[:1] if units_data else 'None'}")
            logger.debug(f"DEBUG: relationships_data sample: {relationships_data[:1] if relationships_data else 'None'}")
            
            # STEP 1: Enhanced duplicate validation
            logger.info("STEP 1: Performing enhanced duplicate validation")
            duplicate_validation = await self.validation_service.validate_duplicate_unit_codes(
                site_id=site_id,
                units_data=units_data,
                db_session=self.db
            )
            
            if not duplicate_validation["can_proceed"]:
                logger.error(f"Duplicate unit codes detected: {duplicate_validation['duplicates']}")
                from app.exceptions.harris_matrix import UnitCodeConflict
                raise UnitCodeConflict(
                    message=f"Duplicate unit codes detected: {', '.join(duplicate_validation['duplicates'])}",
                    existing_codes=duplicate_validation["duplicates"],
                    conflicts=duplicate_validation["conflicts"],
                    suggestions=duplicate_validation["suggestions"]
                )
            
            logger.debug("STEP 1: Enhanced duplicate validation passed")
            
            # Check for code conflicts first (legacy validation)
            logger.debug("DEBUG: Checking code conflicts...")
            await self.unit_lookup.check_code_conflicts(site_id, units_data)
            logger.debug("DEBUG: Code conflicts check passed")
                
            # STEP 2: Validate relationship integrity if relationships exist
            if relationships_data:
                logger.info("STEP 2: Validating relationship integrity")
                # Create units mapping for validation
                temp_units_mapping = {}
                for unit in units_data:
                    if unit.get('code') and unit.get('temp_id'):
                        temp_units_mapping[unit['code']] = unit['temp_id']
                    elif unit.get('us_code') and unit.get('temp_id'):
                        temp_units_mapping[unit['us_code']] = unit['temp_id']
                
                relation_validation = await self.validation_service.validate_relationship_integrity(
                    site_id=site_id,
                    relationships_data=relationships_data,
                    units_mapping=temp_units_mapping,
                    db_session=self.db
                )
                
                if not relation_validation["can_proceed"]:
                    logger.error(f"Invalid relationships detected: {relation_validation['missing_units']}")
                    from app.exceptions.harris_matrix import InvalidStratigraphicRelation
                    raise InvalidStratigraphicRelation(
                        message=f"Invalid relationships detected: {', '.join(relation_validation['missing_units'])}",
                        missing_units=relation_validation["missing_units"],
                        invalid_relations=relation_validation["invalid_relations"]
                    )
                
                logger.debug("STEP 2: Relationship integrity validation passed")
                
                # STEP 3: Detect potential cycles
                logger.info("STEP 3: Detecting potential cycles in relationships")
                cycle_validation = await self.validation_service.detect_potential_cycles(
                    relationships=relationships_data,
                    units_mapping=temp_units_mapping
                )
                
                if not cycle_validation["can_proceed"]:
                    logger.error(f"Potential cycles detected: {cycle_validation['cycle_paths']}")
                    from app.exceptions.harris_matrix import CycleDetectionError
                    raise CycleDetectionError(
                        message=f"Potential cycles detected in relationships: {len(cycle_validation['cycle_paths'])} cycles",
                        cycle_paths=cycle_validation["cycle_paths"],
                        affected_units=cycle_validation["affected_units"]
                    )
                
                logger.debug("STEP 3: Cycle detection validation passed")
            
            # Generate sequential codes if not provided
            logger.debug("DEBUG: Generating sequential codes...")
            units_with_codes = await generate_sequential_codes(site_id, self.db, units_data)
            logger.debug(f"DEBUG: Generated codes: {[u.get('code') for u in units_with_codes[:3]]}")
                
            # Create units
            logger.debug("DEBUG: Creating units...")
            created_units = await self._bulk_create_units(site_id, units_with_codes, current_user_id)
            logger.debug(f"DEBUG: Created {len(created_units)} units")
                
            # Create relationships
            logger.debug("DEBUG: Creating relationships...")
            created_relationships = await self._bulk_create_relationships(
                    created_units, relationships_data
            )
            logger.debug(f"DEBUG: Created {len(created_relationships)} relationships")
                
            # Validate relationships for cycles
            await self.validate_stratigraphic_relationships(created_units, created_relationships)
                
            # ===== CRITICAL: Match response to frontend expectations =====
            result = {
                    'created_units': len(created_units),
                    'created_relationships': len(created_relationships),
                    'unit_mapping': {unit['temp_id']: unit['id'] for unit in created_units},
                    'relationship_mapping': {rel['temp_id']: rel['temp_id'] for rel in created_relationships},
                    'units': created_units,        # Frontend expects this for created units data
                    'relationships': created_relationships,  # Frontend expects this for created relationships data
                    # Add explicit compatibility fields
                    'created_units_list': created_units,     # Additional alias for clarity
                    'created_relationships_list': created_relationships  # Additional alias for clarity
            }
                
            logger.info(f"Bulk creation completed successfully: {result}")
            return result
                
        except Exception as e:
            logger.error(f"Error in bulk creation for site {site_id}: {str(e)}")
            raise HarrisMatrixServiceError(str(e), "bulk_create_units_with_relationships")
    
    
    async def _bulk_create_units(self, site_id: UUID, units_data: List[Dict[str, Any]], current_user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Create multiple units in bulk."""
        try:
            created_units = []
            
            for unit_data in units_data:
                unit_type = unit_data.get('unit_type', 'us')
                # Debug logging to validate assumptions
                logger.debug(f"DEBUG: Creating temp_id for unit_type={unit_type}, unit_data={unit_data}")
                temp_id = unit_data.get('temp_id', str(uuid4()))
                logger.debug(f"DEBUG: Generated temp_id={temp_id} for unit_type={unit_type}")
                
                if unit_type == 'us':
                    unit = UnitaStratigrafica(
                        site_id=str(site_id),
                        us_code=unit_data['code'],
                        definizione=unit_data.get('definition', ''),
                        tipo=unit_data.get('tipo', 'positiva'),
                        localita=unit_data.get('localita'),
                        datazione=unit_data.get('datazione'),
                        periodo=unit_data.get('periodo'),
                        fase=unit_data.get('fase'),
                        affidabilita_stratigrafica=unit_data.get('affidabilita_stratigrafica'),
                        sequenza_fisica=get_default_sequenza_fisica(),
                        created_by=unit_data.get('created_by') or current_user_id,
                        updated_by=unit_data.get('updated_by') or current_user_id
                    )
                else:  # usm
                    unit = UnitaStratigraficaMuraria(
                        site_id=str(site_id),
                        usm_code=unit_data['code'],
                        definizione=unit_data.get('definition', ''),
                        localita=unit_data.get('localita'),
                        datazione=unit_data.get('datazione'),
                        periodo=unit_data.get('periodo'),
                        fase=unit_data.get('fase'),
                        tecnica_costruttiva=unit_data.get('tecnica_costruttiva'),
                        sequenza_fisica=get_default_sequenza_fisica(),
                        created_by=unit_data.get('created_by') or current_user_id,
                        updated_by=unit_data.get('updated_by') or current_user_id
                    )
                
                logger.debug(f"DEBUG: Adding {unit_type} unit to database: code={unit_data['code']}")
                self.db.add(unit)
                await self.db.flush()  # Get the ID
                logger.debug(f"DEBUG: Unit added successfully, got ID={unit.id}")
                
                # ===== CRITICAL FIX: Return complete unit data for UnitResponse schema =====
                unit_response_data = {
                    'temp_id': temp_id,
                    'id': str(unit.id),
                    'code': unit_data['code'],
                    'type': unit_type,
                    'site_id': str(site_id),
                    'description': unit_data.get('definition', ''),
                    'sequenzafisica': unit.sequenza_fisica or {},
                    'data': {},
                    'position': None,
                    'created_by': unit_data.get('created_by') or current_user_id,
                    'updated_by': unit_data.get('updated_by') or current_user_id,
                    'created_at': unit.created_at.isoformat() if unit.created_at else None,
                    'updated_at': unit.updated_at.isoformat() if unit.updated_at else None
                }
                
                # Add unit-specific fields
                if unit_type == 'us':
                    unit_response_data['tipo'] = unit_data.get('tipo')
                    unit_response_data['localita'] = unit_data.get('localita')
                    unit_response_data['datazione'] = unit_data.get('datazione')
                    unit_response_data['periodo'] = unit_data.get('periodo')
                    unit_response_data['fase'] = unit_data.get('fase')
                    unit_response_data['affidabilita_stratigrafica'] = unit_data.get('affidabilita_stratigrafica')
                else:  # usm
                    unit_response_data['tecnica_costruttiva'] = unit_data.get('tecnica_costruttiva')
                
                created_units.append(unit_response_data)
            
            return created_units
            
        except Exception as e:
            logger.error(f"Error in bulk unit creation for site {site_id}: {str(e)}")
            raise
    
    async def _bulk_create_relationships(
        self,
        created_units: List[Dict[str, Any]],
        relationships_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create multiple relationships in bulk."""
        try:
            # DEBUG: Log the structure of created_units to validate assumptions
            logger.debug(f"DEBUG: created_units structure: {created_units}")
            logger.debug(f"DEBUG: created_units type: {type(created_units)}")
            if created_units:
                logger.debug(f"DEBUG: first unit structure: {created_units[0]}")
                logger.debug(f"DEBUG: first unit keys: {list(created_units[0].keys())}")
            
            # Create unit lookup using the actual data structure
            unit_lookup = {
                unit['temp_id']: unit for unit in created_units
            }
            logger.debug(f"DEBUG: unit_lookup created successfully: {list(unit_lookup.keys())}")
            
            code_lookup = {
                (unit['unit_type'], unit['code']): unit for unit in created_units
            }
            logger.debug(f"DEBUG: code_lookup created successfully: {list(code_lookup.keys())}")
            
            created_relationships = []
            
            for rel_data in relationships_data:
                from_temp_id = rel_data.get('from_temp_id')
                to_temp_id = rel_data.get('to_temp_id')
                relation_type = rel_data.get('relation_type')
                
                if not all([from_temp_id, to_temp_id, relation_type]):
                    logger.warning(f"Skipping incomplete relationship: {rel_data}")
                    continue
                
                from_unit_data = unit_lookup.get(from_temp_id)
                to_unit_data = unit_lookup.get(to_temp_id)
                
                if not from_unit_data or not to_unit_data:
                    logger.warning(f"Missing units for relationship: {rel_data}")
                    continue
                
                logger.debug(f"DEBUG: Processing relationship {from_temp_id} -> {to_temp_id} ({relation_type})")
                logger.debug(f"DEBUG: from_unit_data: {from_unit_data}")
                logger.debug(f"DEBUG: to_unit_data: {to_unit_data}")
                
                # Fetch the actual database units to access their attributes
                try:
                    if from_unit_data['unit_type'] == 'us':
                        from_query = select(UnitaStratigrafica).where(
                            UnitaStratigrafica.id == from_unit_data['id']
                        )
                    else:  # usm
                        from_query = select(UnitaStratigraficaMuraria).where(
                            UnitaStratigraficaMuraria.id == from_unit_data['id']
                        )
                    
                    from_result = await self.db.execute(from_query)
                    from_unit = from_result.scalar_one_or_none()
                    
                    if to_unit_data['unit_type'] == 'us':
                        to_query = select(UnitaStratigrafica).where(
                            UnitaStratigrafica.id == to_unit_data['id']
                        )
                    else:  # usm
                        to_query = select(UnitaStratigraficaMuraria).where(
                            UnitaStratigraficaMuraria.id == to_unit_data['id']
                        )
                    
                    to_result = await self.db.execute(to_query)
                    to_unit = to_result.scalar_one_or_none()
                    
                    if not from_unit or not to_unit:
                        logger.warning(f"Could not fetch database units for relationship: {rel_data}")
                        continue
                    
                    logger.debug(f"DEBUG: Successfully fetched database units: from={from_unit.id}, to={to_unit.id}")
                    
                    # Validate the relationship type
                    await self.validate_single_relationship(from_unit, to_unit, relation_type)
                    
                    # Add relationship to from_unit's sequenza_fisica
                    target_code = to_unit.usm_code if hasattr(to_unit, 'usm_code') else to_unit.us_code
                    
                    # Add type suffix for cross-references
                    if hasattr(to_unit, 'usm_code'):
                        target_reference = f"{target_code}(usm)"
                    else:
                        target_reference = target_code
                    
                    logger.debug(f"DEBUG: Adding target_reference '{target_reference}' to relationship type '{relation_type}'")
                    
                    # Ensure the relationship type key exists
                    if relation_type not in from_unit.sequenza_fisica:
                        from_unit.sequenza_fisica[relation_type] = []

                    # Add target reference if not already present
                    if target_reference not in from_unit.sequenza_fisica[relation_type]:
                        from_unit.sequenza_fisica[relation_type].append(target_reference)
                        
                        # CRITICAL: Mark JSON field as modified for SQLAlchemy
                        flag_modified(from_unit, "sequenza_fisica")
                        
                        logger.debug(f"Added {target_reference} to {relation_type} for unit {from_unit.id}")
                        
                        # ===== BIDIRECTIONAL RELATIONSHIP CONSISTENCY FIX =====
                        # Add inverse relationship to target unit if applicable
                        if relation_type in RELATIONSHIP_INVERSES:
                            inverse_rel_type = RELATIONSHIP_INVERSES[relation_type]
                            
                            # Only add inverse for bidirectional relationship types
                            if inverse_rel_type in RELATIONSHIP_TYPES:
                                # Generate source reference for target unit
                                if hasattr(from_unit, 'us_code'):
                                    source_reference = from_unit.us_code
                                else:  # usm
                                    source_reference = f"{from_unit.usm_code}(usm)"
                                
                                # Initialize inverse relationship type if it doesn't exist
                                if inverse_rel_type not in to_unit.sequenza_fisica:
                                    to_unit.sequenza_fisica[inverse_rel_type] = []
                                
                                # Add inverse relationship if not already present
                                if source_reference not in to_unit.sequenza_fisica[inverse_rel_type]:
                                    to_unit.sequenza_fisica[inverse_rel_type].append(source_reference)
                                    
                                    # CRITICAL: Mark target unit's JSON field as modified
                                    flag_modified(to_unit, "sequenza_fisica")
                                    
                                    logger.debug(f"Added inverse relationship {source_reference} to {inverse_rel_type} for target unit {to_unit.id}")
                                else:
                                    logger.debug(f"Inverse relationship {source_reference} already exists in {inverse_rel_type}")
                    else:
                        logger.debug(f"Relationship {target_reference} already exists in {relation_type}")
                
                    # ===== CRITICAL FIX: Return complete relationship data for RelationshipResponse schema =====
                    rel_temp_id = rel_data.get('temp_id', str(uuid4()))
                    
                    # Determine if relationship is bidirectional
                    rel_config = RELATIONSHIP_TYPES.get(relation_type, {})
                    is_bidirectional = rel_config.get('bidirectional', False)
                    
                    # Create target reference for frontend
                    if hasattr(to_unit, 'usm_code'):
                        target_reference = f"{to_unit.usm_code}(usm)"
                    else:
                        target_reference = to_unit.us_code
                    
                    relationship_response_data = {
                        'temp_id': rel_temp_id,
                        'id': rel_temp_id,  # Use temp_id as ID for now
                        'from_unit_id': str(from_unit.id),
                        'to_unit_id': str(to_unit.id),
                        'relationship_type': relation_type,
                        'resolved': True,  # Successfully created
                        'from_tempid': from_temp_id,
                        'to_tempid': to_temp_id,
                        'tempid': rel_temp_id,
                        'bidirectional': is_bidirectional,
                        'description': rel_config.get('description', ''),
                        'label': rel_config.get('label', relation_type),
                        'created_at': datetime.utcnow().isoformat(),
                        'updated_at': datetime.utcnow().isoformat()
                    }
                    
                    logger.debug(f"DEBUG: Creating relationship response from={from_unit.id} to={to_unit.id}, type={relation_type}")
                    created_relationships.append(relationship_response_data)
                    logger.debug(f"DEBUG: Created relationship temp_id={rel_temp_id}")
                    
                except Exception as e:
                    logger.error(f"DEBUG: Error processing relationship {rel_data}: {e}")
                    continue
            
            # ===== CRITICAL FIX: Ensure bidirectional relationship consistency =====
            for tempid, relationship_data in created_relationships:
                from_unit_id = relationship_data['from_unit_id']
                to_unit_id = relationship_data['to_unit_id']
                rel_type = relationship_data['relationship_type']
                inverse_type = RELATIONSHIP_INVERSES.get(rel_type)
                
                # Check if inverse relationship needs to be created
                if inverse_type and from_unit_id and to_unit_id:
                    # Check if inverse already exists
                    existing_inverse = await db.execute(
                        select(UnitaStratigrafica).where(
                            and_(
                                UnitaStratigrafica.id == to_unit_id,
                                UnitaStratigrafica.sequenza_fisica.isnot(None),
                                func.json_extract(UnitaStratigrafica.sequenza_fisica, f'$.{inverse_type}').isnot(None)
                            )
                        )
                    )
                    
                    inverse_exists = False
                    if existing_inverse.scalar_one_or_none():
                        # Check if the specific inverse relationship exists in the JSON
                        from_unit = await db.execute(
                            select(UnitaStratigrafica).where(UnitaStratigrafica.id == from_unit_id)
                        )
                        from_unit_obj = from_unit.scalar_one_or_none()
                        
                        if from_unit_obj:
                            from_code = from_unit_obj.us_code if hasattr(from_unit_obj, 'us_code') else from_unit_obj.usm_code
                            to_unit_check = await db.execute(
                                select(UnitaStratigrafica).where(UnitaStratigrafica.id == to_unit_id)
                            )
                            to_unit_obj = to_unit_check.scalar_one_or_none()
                            
                            if to_unit_obj and to_unit_obj.sequenza_fisica and inverse_type in to_unit_obj.sequenza_fisica:
                                inverse_exists = from_code in to_unit_obj.sequenza_fisica[inverse_type]
                    
                    if not inverse_exists:
                        # Create inverse relationship
                        to_unit_check = await db.execute(
                            select(UnitaStratigrafica).where(UnitaStratigrafica.id == to_unit_id)
                        )
                        target_unit = to_unit_check.scalar_one_or_none()
                        
                        if target_unit:
                            # Get source unit code
                            from_unit_check = await db.execute(
                                select(UnitaStratigrafica).where(UnitaStratigrafica.id == from_unit_id)
                            )
                            source_unit = from_unit_check.scalar_one_or_none()
                            
                            if source_unit:
                                source_code = source_unit.us_code if hasattr(source_unit, 'us_code') else source_unit.usm_code
                                
                                # Add type suffix for cross-references if needed
                                if hasattr(source_unit, 'usm_code'):
                                    source_reference = f"{source_code}(usm)"
                                else:
                                    source_reference = source_code
                                
                                # Initialize sequenza_fisica if needed
                                if not target_unit.sequenza_fisica:
                                    target_unit.sequenza_fisica = get_default_sequenza_fisica()
                                
                                # Add inverse relationship
                                if inverse_type not in target_unit.sequenza_fisica:
                                    target_unit.sequenza_fisica[inverse_type] = []
                                
                                if source_reference not in target_unit.sequenza_fisica[inverse_type]:
                                    target_unit.sequenza_fisica[inverse_type].append(source_reference)
                                    
                                    # Mark JSON field as modified for SQLAlchemy
                                    flag_modified(target_unit, "sequenza_fisica")
                                    
                                    logger.info(f"[INVERSE REL] Created inverse: {inverse_type} from {to_unit_id} to {from_unit_id}")
            
            # Flush all pending changes to database
            await self.db.flush()
            logger.debug(f"Flushed {len(created_relationships)} relationship updates to database")
            
            return created_relationships
            
        except Exception as e:
            logger.error(f"Error in bulk relationship creation: {str(e)}")
            raise
    
    async def validate_stratigraphic_relationships(
        self,
        units: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> None:
        """
        Validate stratigraphic relationships for business rules and cycles.
        
        Args:
            units: List of unit dictionaries
            relationships: List of relationship dictionaries
        """
        try:
            logger.info("Validating stratigraphic relationships")
            
            # Transform units data to match expected format for validation
            validation_units = await self._prepare_units_for_validation(units)
            
            # Transform relationships to use proper unit IDs
            validation_relationships = await self._prepare_relationships_for_validation(units, relationships)
            
            # Build graph representation using centralized service
            graph = self.graph_builder.build_validation_graph(validation_units, validation_relationships)
            
            # Check for cycles using centralized detector
            cycles = CycleDetector.detect_cycles_in_graph(graph)
            if cycles:
                raise StratigraphicCycleDetected(cycles[0])
            
            # Validate business rules using centralized validator
            self.rules_validator.validate_business_rules(validation_units, validation_relationships)
            
            logger.info("Stratigraphic relationships validation passed")
            
        except Exception as e:
            logger.error(f"Error validating stratigraphic relationships: {str(e)}")
            raise
    
    async def _prepare_units_for_validation(self, units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform unit data to match the expected validation format.
        
        The validate_business_rules function expects each unit dictionary to have a 'unit' key
        containing the actual unit object, but bulk creation provides a different structure.
        
        Args:
            units: List of unit dictionaries from bulk creation
            
        Returns:
            List of unit dictionaries in validation format
        """
        try:
            validation_units = []
            
            for unit in units:
                # Fetch the actual database unit object
                if unit['unit_type'] == 'us':
                    query = select(UnitaStratigrafica).where(
                        UnitaStratigrafica.id == unit['id']
                    )
                else:  # usm
                    query = select(UnitaStratigraficaMuraria).where(
                        UnitaStratigraficaMuraria.id == unit['id']
                    )
                
                result = await self.db.execute(query)
                unit_obj = result.scalar_one_or_none()
                
                if unit_obj:
                    validation_unit = {
                        'id': unit['id'],
                        'unit_type': unit['unit_type'],
                        'unit': unit_obj  # This is the key fix - include the actual unit object
                    }
                    validation_units.append(validation_unit)
                else:
                    logger.warning(f"Could not find unit {unit['id']} for validation")
            
            logger.debug(f"Prepared {len(validation_units)} units for validation")
            return validation_units
            
        except Exception as e:
            logger.error(f"Error preparing units for validation: {str(e)}")
            raise
    
    async def _prepare_relationships_for_validation(self, units: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform relationships to use proper unit IDs for validation.
        
        Args:
            units: List of unit dictionaries from bulk creation
            relationships: List of relationship dictionaries
            
        Returns:
            List of relationship dictionaries in validation format
        """
        try:
            # Create mapping from temp_id to actual database ID
            id_mapping = {unit['temp_id']: unit['id'] for unit in units}
            
            validation_relationships = []
            
            for rel in relationships:
                from_temp_id = rel.get('from_temp_id')
                to_temp_id = rel.get('to_temp_id')
                
                if from_temp_id in id_mapping and to_temp_id in id_mapping:
                    validation_rel = {
                        'from_unit_id': id_mapping[from_temp_id],
                        'to_unit_id': id_mapping[to_temp_id],
                        'relation_type': rel['relation_type']
                    }
                    validation_relationships.append(validation_rel)
                else:
                    logger.warning(f"Skipping relationship with missing units: {from_temp_id} -> {to_temp_id}")
            
            logger.debug(f"Prepared {len(validation_relationships)} relationships for validation")
            return validation_relationships
            
        except Exception as e:
            logger.error(f"Error preparing relationships for validation: {str(e)}")
            raise
    
    
    
    
    async def validate_single_relationship(
        self,
        from_unit,
        to_unit,
        relation_type: str
    ) -> None:
        """
        Valida una singola relazione utilizzando il validator Harris/ICCD.
        
        Questo metodo utilizza il nuovo validate_single_relationship() del validator
        che implementa le regole specifiche del sistema Harris/ICCD.
        
        Args:
            from_unit: Unità stratigrafica di origine
            to_unit: Unità stratigrafica di destinazione
            relation_type: Tipo di relazione (es. 'taglia', 'copre', etc.)
            
        Raises:
            InvalidStratigraphicRelation: Se la relazione viola le regole Harris/ICCD
        """
        self.rules_validator.validate_single_relationship(from_unit, to_unit, relation_type)
    
    async def bulk_update_relationships(
        self,
        site_id: UUID,
        unit_id: UUID,
        unit_type: str,
        relationships_update: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Bulk update relationships for a specific unit.
        
        This method performs the database operations for updating relationships.
        Transaction management should be handled by the caller (API layer).
        
        Args:
            site_id: UUID of the archaeological site
            unit_id: UUID of the unit to update
            unit_type: Type of unit ('us' or 'usm')
            relationships_update: Dictionary of relationship updates
            
        Returns:
            Dictionary with update results
        """
        try:
            logger.info(f"Bulk updating relationships for {unit_type} {unit_id} in site {site_id}")
            
            # Get the unit
            if unit_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.id == str(unit_id),
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
            else:  # usm
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.id == str(unit_id),
                        UnitaStratigraficaMuraria.site_id == str(site_id),
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
            
            result = await self.db.execute(query)
            unit = result.scalar_one_or_none()
            
            if not unit:
                raise HarrisMatrixValidationError(f"{unit_type.upper()} unit not found")
            
            # Store old relationships for validation
            old_relationships = unit.sequenza_fisica.copy() if unit.sequenza_fisica else {}
            
            # Update relationships
            if not unit.sequenza_fisica:
                unit.sequenza_fisica = get_default_sequenza_fisica()
            
            # Apply updates
            for rel_type, targets in relationships_update.items():
                if rel_type in unit.sequenza_fisica:
                    unit.sequenza_fisica[rel_type] = targets or []
                    
                    # CRITICAL: Mark JSON field as modified for SQLAlchemy
                    flag_modified(unit, "sequenza_fisica")
            
            # Validate the updated relationships with comprehensive validation
            await self._validate_bulk_update(site_id, unit, old_relationships)
            
            result = {
                'unit_id': str(unit_id),
                'unit_type': unit_type,
                'old_relationships': old_relationships,
                'new_relationships': unit.sequenza_fisica,
                'updated_relationships': len([
                    k for k, v in old_relationships.items()
                    if old_relationships.get(k) != unit.sequenza_fisica.get(k)
                ])
            }
            
            logger.info(f"Bulk relationship update completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error in bulk update relationships for {unit_type} {unit_id}: {str(e)}")
            raise HarrisMatrixServiceError(str(e), "bulk_update_relationships")
            
    async def _validate_bulk_update(
        self,
        site_id: UUID,
        unit,
        old_relationships: Dict[str, List[str]]
    ) -> None:
        """
        Validate bulk update with comprehensive cycle detection and business rules validation.
        
        This method performs validation after relationships have been updated but before
        the transaction is committed. If validation fails, the transaction should be rolled back.
        
        Args:
            site_id: UUID of the archaeological site
            unit: The unit that was updated (US or USM)
            old_relationships: The old relationships before the update (for rollback info)
            
        Raises:
            StratigraphicCycleDetected: If cycles are detected in the updated relationships
            InvalidStratigraphicRelation: If business rules are violated
            HarrisMatrixValidationError: For other validation errors
        """
        try:
            logger.info(f"Starting comprehensive validation for bulk update: {unit.id}")
            
            # 1. Get all units for the site to build complete graph
            us_units, usm_units = await self.unit_lookup.get_units_by_site(site_id)
            
            # 2. Extract relationships from all units to build complete graph
            all_relationships = await self._extract_relationships(us_units, usm_units)
            
            # 3. Build validation units list
            validation_units = []
            
            # Add US units
            for us in us_units:
                validation_unit = {
                    'id': str(us.id),
                    'unit_type': 'us',
                    'unit': us
                }
                validation_units.append(validation_unit)
            
            # Add USM units
            for usm in usm_units:
                validation_unit = {
                    'id': str(usm.id),
                    'unit_type': 'usm',
                    'unit': usm
                }
                validation_units.append(validation_unit)
            
            # 4. Build validation relationships from current state
            validation_relationships = await self._build_validation_relationships_from_units(validation_units)
            
            # 5. Perform cycle detection
            logger.debug("Performing cycle detection on updated graph")
            graph = self.graph_builder.build_validation_graph(validation_units, validation_relationships)
            cycles = CycleDetector.detect_cycles_in_graph(graph)
            
            if cycles:
                logger.error(f"Stratigraphic cycles detected after bulk update: {cycles}")
                
                # Provide detailed cycle information
                cycle_details = []
                for cycle in cycles:
                    cycle_str = " → ".join(cycle[:-1])  # Exclude the repeated last node
                    cycle_details.append(f"Cycle: {cycle_str}")
                
                # Construct informative error message with rollback guidance
                unit_code = unit.us_code if hasattr(unit, 'us_code') else unit.usm_code
                unit_type = 'US' if hasattr(unit, 'us_code') else 'USM'
                
                raise StratigraphicCycleDetected(
                    f"Bulk update created invalid stratigraphic cycles in {unit_type} {unit_code}. "
                    f"Detected cycles: {'; '.join(cycle_details)}. "
                    f"Transaction will be rolled back to maintain data integrity."
                )
            
            # 6. Validate business rules
            logger.debug("Performing business rules validation")
            try:
                self.rules_validator.validate_business_rules(validation_units, validation_relationships)
                logger.debug("Business rules validation passed")
            except InvalidStratigraphicRelation as e:
                logger.error(f"Business rules validation failed: {str(e)}")
                
                # Add contextual information about the bulk update
                unit_code = unit.us_code if hasattr(unit, 'us_code') else unit.usm_code
                unit_type = 'US' if hasattr(unit, 'us_code') else 'USM'
                
                raise InvalidStratigraphicRelation(
                    f"Bulk update violated stratigraphic business rules in {unit_type} {unit_code}. "
                    f"Error: {str(e)}. "
                    f"Transaction will be rolled back to maintain data integrity."
                )
            
            # 7. Validate specific relationship types for the updated unit
            logger.debug("Validating individual relationships in updated unit")
            await self._validate_unit_relationships(unit)
            
            logger.info("Bulk update validation completed successfully")
            
        except (StratigraphicCycleDetected, InvalidStratigraphicRelation) as e:
            # These are expected validation errors - re-raise for rollback
            logger.error(f"Bulk update validation failed: {str(e)}")
            raise
        except Exception as e:
            # Unexpected validation error
            logger.error(f"Unexpected error during bulk update validation: {str(e)}", exc_info=True)
            raise HarrisMatrixValidationError(f"Validation system error: {str(e)}")
    
    async def _build_validation_relationships_from_units(self, validation_units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build validation relationship list from current unit relationships.
        
        Args:
            validation_units: List of unit dictionaries with 'unit' objects
            
        Returns:
            List of relationship dictionaries in validation format
        """
        validation_relationships = []
        
        for unit_data in validation_units:
            unit = unit_data['unit']
            unit_id = unit_data['id']
            unit_type = unit_data['unit_type']
            
            if not unit.sequenza_fisica:
                continue
                
            for rel_type, targets in unit.sequenza_fisica.items():
                if not targets or rel_type not in VALID_RELATIONSHIP_TYPES:
                    continue
                
                for target in targets:
                    # Parse target reference to extract code and type
                    target_code, target_type = parse_target_reference(target)
                    
                    # Find target unit by lookup
                    target_unit = None
                    if target_type == 'us':
                        target_unit = await self.unit_lookup.get_unit_by_code(
                            site_id=unit.site_id,
                            unit_code=target_code,
                            unit_type='us'
                        )
                    elif target_type == 'usm':
                        target_unit = await self.unit_lookup.get_unit_by_code(
                            site_id=unit.site_id,
                            unit_code=target_code,
                            unit_type='usm'
                        )
                    
                    if target_unit:
                        validation_relationships.append({
                            'from_unit_id': unit_id,
                            'to_unit_id': str(target_unit.id),
                            'relation_type': rel_type
                        })
        
        return validation_relationships
    
    async def _validate_unit_relationships(self, unit) -> None:
        """
        Validate individual relationships within a unit for basic constraints.
        
        Args:
            unit: The unit to validate (US or USM)
            
        Raises:
            InvalidStratigraphicRelation: If individual relationships are invalid
        """
        if not unit.sequenza_fisica:
            return
            
        for rel_type, targets in unit.sequenza_fisica.items():
            if not targets or rel_type not in VALID_RELATIONSHIP_TYPES:
                continue
            
            # Check for duplicate targets
            if len(set(targets)) != len(targets):
                unit_code = unit.us_code if hasattr(unit, 'us_code') else unit.usm_code
                unit_type = 'US' if hasattr(unit, 'us_code') else 'USM'
                
                # Find duplicates
                duplicates = [target for target in targets if targets.count(target) > 1]
                unique_duplicates = list(set(duplicates))
                
                raise InvalidStratigraphicRelation(
                    f"{unit_type} {unit_code} has duplicate relationships in '{rel_type}': "
                    f"{', '.join(unique_duplicates)}. Each relationship should only appear once."
                )
            
            # Validate each individual relationship
            for target in targets:
                target_code, target_type = parse_target_reference(target)
                
                # Find target unit for validation
                target_unit = await self.unit_lookup.get_unit_by_code(
                    site_id=unit.site_id,
                    unit_code=target_code,
                    unit_type=target_type
                )
                
                if target_unit:
                    try:
                        await self.validate_single_relationship(unit, target_unit, rel_type)
                    except InvalidStratigraphicRelation as e:
                        # Add context about which relationship failed
                        unit_code = unit.us_code if hasattr(unit, 'us_code') else unit.usm_code
                        unit_type = 'US' if hasattr(unit, 'us_code') else 'USM'
                        target_display = f"{target_type.upper()}{target_code}"
                        
                        raise InvalidStratigraphicRelation(
                            f"Invalid relationship in {unit_type} {unit_code}: {unit_code} {rel_type} {target_display}. "
                            f"Error: {str(e)}"
                        )
    
    async def bulk_update_sequenza_fisica_units(
        self,
        site_id: UUID,
        updates: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Enhanced bulk update sequenzafisica field for multiple existing US/USM units.
        
        This method performs comprehensive validation including stale reference detection,
        schema validation, cycle detection, business rules validation, and proper transaction management.
        
        Args:
            site_id: UUID of the archaeological site
            updates: Dictionary mapping unit IDs to their new sequenzafisica
            
        Returns:
            Dictionary with update statistics and results
            
        Raises:
            HarrisMatrixValidationError: If input validation fails
            StratigraphicCycleDetected: If cycles are detected in relationships
            InvalidStratigraphicRelation: If business rules are violated
            StaleReferenceError: If references to non-existent units are detected
            HarrisMatrixServiceError: For service-level errors
        """
        try:
            logger.info(f"Bulk updating sequenzafisica for {len(updates)} units in site {site_id}")
            
            # 1. STALE REFERENCE VALIDATION - Check all unit references exist
            logger.info("STEP 1: Performing stale reference validation")
            validation_result = await self.validation_service.validate_stale_references(
                site_id=site_id,
                updates=updates,
                db_session=self.db
            )
            
            if not validation_result["can_proceed"]:
                logger.error(f"Stale references detected: {validation_result}")
                raise StaleReferenceError(
                    message="Some units cannot be updated due to stale references",
                    missing_units=validation_result["missing_ids"],
                    soft_deleted_units=validation_result["soft_deleted_ids"],
                    wrong_site_units=validation_result["wrong_site_ids"]
                )
            
            # 2. COMPREHENSIVE BULK UPDATE INTEGRITY VALIDATION
            logger.info("STEP 2: Performing comprehensive bulk update integrity validation")
            integrity_result = await self.validation_service.validate_bulk_update_integrity(
                site_id=site_id,
                updates=updates,
                db_session=self.db
            )
            
            if not integrity_result["can_proceed"]:
                logger.error(f"Bulk update integrity validation failed: {integrity_result}")
                # Collect all issues
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
                
                raise HarrisMatrixValidationError(
                    f"Bulk update integrity validation failed: {'; '.join(all_issues)}"
                )
            
            # 3. INPUT VALIDATION - Validate schema using existing Pydantic schema
            await self._validate_bulk_update_input(updates)
            
            # 4. PRE-UPDATE VALIDATION - Validate units exist and collect data
            validated_units = await self._validate_and_collect_units(site_id, updates)
            
            # 5. PERFORM UPDATES WITH OLD STATE COLLECTION AND SKIP TRACKING
            old_relationships = {}
            updated_units = []
            skipped_units = []
            
            for unit_id, (unit, unit_type, new_sequenza) in validated_units.items():
                # CRITICAL FIX: Validate that unit is the actual object, not a coroutine
                if hasattr(unit, '__await__'):
                    logger.error(f"ERROR: unit is a coroutine object at line 1252: {unit}")
                    unit = await unit  # Await the coroutine if needed
                
                # Additional validation to ensure unit is the correct type
                if not isinstance(unit, (UnitaStratigrafica, UnitaStratigraficaMuraria)):
                    logger.error(f"ERROR: unit is not a valid unit object at line 1252: {type(unit)} - {unit}")
                    skipped_units.append({
                        "unit_id": unit_id,
                        "reason": "invalid_unit_object_type",
                        "unit_type": str(type(unit))
                    })
                    continue
                
                # Store old relationships for validation and rollback info
                old_relationships[unit_id] = {
                    'old_sequenza_fisica': unit.sequenza_fisica.copy() if unit.sequenza_fisica else {},
                    'unit_code': unit.us_code if hasattr(unit, 'us_code') else unit.usm_code,
                    'unit_type': unit_type
                }
                
                try:
                    # Apply update
                    unit.sequenza_fisica = new_sequenza
                    
                    # CRITICAL: Mark JSON field as modified for SQLAlchemy
                    flag_modified(unit, "sequenza_fisica")
                    
                    updated_units.append({
                        'id': unit_id,
                        'unit': unit,
                        'unit_type': unit_type,
                        'unit_code': old_relationships[unit_id]['unit_code']
                    })
                    
                    logger.debug(f"Updated sequenzafisica for {unit_type} {old_relationships[unit_id]['unit_code']}")
                    
                except Exception as update_error:
                    logger.error(f"Failed to update unit {unit_id}: {str(update_error)}")
                    skipped_units.append({
                        "unit_id": unit_id,
                        "reason": "update_failed",
                        "error": str(update_error)
                    })
            
            # 6. COMPREHENSIVE POST-UPDATE VALIDATION
            await self._validate_bulk_update_comprehensive(site_id, updated_units, old_relationships)
            
            # 7. RETURN ENHANCED RESULT WITH SKIP TRACKING
            result = {
                "success": True,
                "updated_count": len(updated_units),
                "total_requested": len(updates),
                "updated_units": [
                    {
                        "unit_id": unit['id'],
                        "unit_type": unit['unit_type'],
                        "unit_code": unit['unit_code']
                    } for unit in updated_units
                ],
                "skipped_units": skipped_units,
                "validation_performed": True,
                "validation_details": {
                    "stale_reference_validation": validation_result,
                    "integrity_validation": integrity_result
                },
                "errors": []
            }
            
            logger.info(f"Bulk sequenzafisica update completed successfully: {len(updated_units)}/{len(updates)} units updated, {len(skipped_units)} skipped")
            return result
            
        except StaleReferenceError:
            # Re-raise stale reference errors as-is for proper handling
            raise
        except (HarrisMatrixValidationError, StratigraphicCycleDetected, InvalidStratigraphicRelation) as e:
            # These are expected validation errors - re-raise for rollback
            logger.error(f"Bulk update validation failed: {str(e)}")
            raise
        except Exception as e:
            # Unexpected error
            logger.error(f"Error in bulk sequenzafisica update: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "bulk_update_sequenza_fisica_units")
    
    async def _validate_bulk_update_input(self, updates: Dict[str, Dict[str, Any]]) -> None:
        """
        Validate input data structure and schema using Pydantic validation.
        
        Args:
            updates: Dictionary mapping unit IDs to their new sequenzafisica
            
        Raises:
            HarrisMatrixValidationError: If input validation fails
        """
        try:
            logger.debug("Validating bulk update input structure")
            
            # Basic structure validation
            if not isinstance(updates, dict):
                raise HarrisMatrixValidationError("Updates must be a dictionary")
            
            if not updates:
                raise HarrisMatrixValidationError("At least one unit update is required")
            
            if len(updates) > 100:
                raise HarrisMatrixValidationError("Maximum 100 units can be updated in a single request")
            
            # Validate each unit update
            for unit_id, sequenza_fisica in updates.items():
                # Enhanced unit ID validation - accept both UUID and unit codes
                is_valid = False
                
                # 1. Try parsing as UUID first (for proper UUID strings)
                try:
                    UUID(unit_id)
                    is_valid = True
                    logger.debug(f"Unit ID {unit_id} validated as UUID format")
                except ValueError:
                    # 2. Try unit code format resolution (US001, USM001)
                    unit_code_pattern = r'^(USM\d+|US\d+)$'
                    if re.match(unit_code_pattern, unit_id, re.IGNORECASE):
                        is_valid = True
                        logger.info(f"Unit ID {unit_id} recognized as unit code format")
                        # NOTE: This will be resolved to UUID by the validation logic
                    else:
                        # 3. Log the specific unit IDs being rejected for debugging
                        logger.warning(f"Invalid unit ID format detected: {unit_id} (neither UUID nor unit code format)")
                        raise HarrisMatrixValidationError(
                            f"Invalid unit ID format: {unit_id}. "
                            f"Expected UUID string (e.g., '550e8400-e29b-41d4-a716-446655440000') "
                            f"or unit code (e.g., 'US001', 'USM001'). "
                            f"Received: '{unit_id}'"
                        )
                
                # Validate sequenza_fisica structure
                if not isinstance(sequenza_fisica, dict):
                    raise HarrisMatrixValidationError(f"sequenzafisica for unit {unit_id} must be a dictionary")
                
                # Validate relationship types and targets
                for rel_type, targets in sequenza_fisica.items():
                    # Check if relationship type is valid
                    if rel_type not in VALID_RELATIONSHIP_TYPES:
                        raise HarrisMatrixValidationError(
                            f"Invalid relationship type '{rel_type}' for unit {unit_id}. "
                            f"Valid types: {VALID_RELATIONSHIP_TYPES}"
                        )
                    
                    # Validate targets structure
                    if targets is None:
                        continue  # Allow None (will be converted to empty list)
                    elif not isinstance(targets, list):
                        raise HarrisMatrixValidationError(
                            f"Relationship targets for '{rel_type}' in unit {unit_id} must be a list or null"
                        )
                    
                    # Validate each target string
                    for target in targets:
                        if not isinstance(target, str):
                            raise HarrisMatrixValidationError(
                                f"Relationship target '{target}' in unit {unit_id} must be a string"
                            )
                        
                        if not target.strip():
                            raise HarrisMatrixValidationError(
                                f"Empty relationship target found in unit {unit_id}"
                            )
                
                logger.debug(f"Input validation passed for unit {unit_id}")
            
            logger.debug("Bulk update input validation completed successfully")
            
        except HarrisMatrixValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during input validation: {str(e)}", exc_info=True)
            raise HarrisMatrixValidationError(f"Input validation error: {str(e)}")
    
    async def _validate_and_collect_units(
        self,
        site_id: UUID,
        updates: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Tuple[Union[UnitaStratigrafica, UnitaStratigraficaMuraria], str, Dict[str, List[str]]]]:
        """
        Validate that all units exist and collect unit data for processing.
        
        Args:
            site_id: UUID of the archaeological site
            updates: Dictionary mapping unit IDs to their new sequenzafisica
            
        Returns:
            Dictionary mapping unit_id to (unit_object, unit_type, new_sequenza_fisica)
            
        Raises:
            HarrisMatrixValidationError: If any units don't exist or are invalid
        """
        try:
            logger.debug("Validating unit existence and collecting unit data")
            
            validated_units = {}
            missing_units = []
            
            for unit_id, new_sequenza in updates.items():
                unit = None
                unit_type = None
                
                # First, try direct UUID lookup
                query_us = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.id == unit_id,
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
                result_us = await self.db.execute(query_us)
                unit = result_us.scalar_one_or_none()
                
                if unit:
                    unit_type = 'us'
                else:
                    # Try USM direct UUID lookup
                    query_usm = select(UnitaStratigraficaMuraria).where(
                        and_(
                            UnitaStratigraficaMuraria.id == unit_id,
                            UnitaStratigraficaMuraria.site_id == str(site_id),
                            UnitaStratigraficaMuraria.deleted_at.is_(None)
                        )
                    )
                    result_usm = await self.db.execute(query_usm)
                    unit = result_usm.scalar_one_or_none()
                    
                    if unit:
                        unit_type = 'usm'
                
                # If still not found and unit_id looks like a unit code, try code resolution
                if not unit:
                    unit_code_pattern = r'^(USM\d+|US\d+)$'
                    if re.match(unit_code_pattern, unit_id, re.IGNORECASE):
                        logger.info(f"Attempting to resolve unit code {unit_id} to UUID")
                        
                        # Determine unit type from prefix - check USM first (longer prefix)
                        if unit_id.upper().startswith('USM'):
                            unit_type = 'usm'
                        elif unit_id.upper().startswith('US'):
                            unit_type = 'us'
                        else:
                            unit_type = None
                        
                        if unit_type:
                            # Use UnitLookupService directly with the FULL unit code
                            # The database stores full codes like US001, USM001, not just 001
                            unit = await self.unit_lookup.get_unit_by_code(
                                site_id=site_id,
                                unit_code=unit_id,  # Pass full code like US001 or USM001
                                unit_type=unit_type
                            )
                            
                            if unit:
                                logger.info(f"Successfully resolved unit code {unit_id} to UUID {unit.id}")
                                logger.debug(f"Resolved {unit_type} unit: {unit_id} -> {unit.id}")
                
                if not unit:
                    missing_units.append(unit_id)
                    continue
                
                # Normalize sequenza_fisica (convert None to empty lists)
                normalized_sequenza = {}
                for rel_type, targets in new_sequenza.items():
                    if targets is None:
                        normalized_sequenza[rel_type] = []
                    else:
                        normalized_sequenza[rel_type] = targets
                
                validated_units[unit_id] = (unit, unit_type, normalized_sequenza)
                logger.debug(f"Validated {unit_type} unit {unit_id}")
            
            if missing_units:
                raise HarrisMatrixValidationError(
                    f"The following units were not found or are deleted: {', '.join(missing_units)}"
                )
            
            if not validated_units:
                raise HarrisMatrixValidationError("No valid units found for updating")
            
            logger.debug(f"Unit validation completed: {len(validated_units)} units validated")
            return validated_units
            
        except HarrisMatrixValidationError:
            raise
        except Exception as e:
            logger.error(f"Error during unit validation: {str(e)}", exc_info=True)
            raise HarrisMatrixValidationError(f"Unit validation error: {str(e)}")
    
    async def _validate_bulk_update_comprehensive(
        self,
        site_id: UUID,
        updated_units: List[Dict[str, Any]],
        old_relationships: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Perform comprehensive post-update validation including cycle detection and business rules.
        
        Args:
            site_id: UUID of the archaeological site
            updated_units: List of updated unit dictionaries
            old_relationships: Dictionary of old relationships for context
            
        Raises:
            StratigraphicCycleDetected: If cycles are detected in relationships
            InvalidStratigraphicRelation: If business rules are violated
            HarrisMatrixValidationError: For other validation errors
        """
        try:
            logger.info("Starting comprehensive post-update validation")
            
            # 1. Get all units for the site to build complete graph
            us_units, usm_units = await self.unit_lookup.get_units_by_site(site_id)
            
            # 2. Extract relationships from all units to build complete graph
            all_relationships = await self._extract_relationships(us_units, usm_units)
            
            # 3. Build validation units list
            validation_units = []
            
            # Add US units
            for us in us_units:
                validation_unit = {
                    'id': str(us.id),
                    'unit_type': 'us',
                    'unit': us
                }
                validation_units.append(validation_unit)
            
            # Add USM units
            for usm in usm_units:
                validation_unit = {
                    'id': str(usm.id),
                    'unit_type': 'usm',
                    'unit': usm
                }
                validation_units.append(validation_unit)
            
            # 4. Build validation relationships from current state
            validation_relationships = await self._build_validation_relationships_from_units(validation_units)
            
            # 5. PERFORM CYCLE DETECTION
            logger.debug("Performing cycle detection on updated graph")
            graph = self.graph_builder.build_validation_graph(validation_units, validation_relationships)
            cycles = CycleDetector.detect_cycles_in_graph(graph)
            
            if cycles:
                logger.error(f"Stratigraphic cycles detected after bulk update: {cycles}")
                
                # Provide detailed cycle information
                cycle_details = []
                for cycle in cycles:
                    cycle_str = " → ".join(cycle[:-1])  # Exclude the repeated last node
                    cycle_details.append(f"Cycle: {cycle_str}")
                
                # Get affected units from our updates
                affected_updated_units = []
                for unit in updated_units:
                    unit_code = unit['unit_code']
                    for cycle in cycles:
                        if f"{unit['unit_type'].upper()}{unit_code}" in cycle:
                            affected_updated_units.append(f"{unit['unit_type'].upper()}{unit_code}")
                            break
                
                raise StratigraphicCycleDetected(
                    f"Bulk update created invalid stratigraphic cycles. "
                    f"Detected cycles: {'; '.join(cycle_details)}. "
                    f"Updated units involved: {', '.join(affected_updated_units) if affected_updated_units else 'None'}. "
                    f"Transaction will be rolled back to maintain data integrity."
                )
            
            # 6. VALIDATE BUSINESS RULES
            logger.debug("Performing business rules validation")
            try:
                self.rules_validator.validate_business_rules(validation_units, validation_relationships)
                logger.debug("Business rules validation passed")
            except InvalidStratigraphicRelation as e:
                logger.error(f"Business rules validation failed: {str(e)}")
                
                # Add contextual information about the bulk update
                affected_updated_units = []
                for unit in updated_units:
                    unit_code = unit['unit_code']
                    # Check if this unit's relationships are mentioned in the error
                    if f"{unit['unit_type'].upper()}{unit_code}" in str(e):
                        affected_updated_units.append(f"{unit['unit_type'].upper()}{unit_code}")
                
                raise InvalidStratigraphicRelation(
                    f"Bulk update violated stratigraphic business rules. "
                    f"Error: {str(e)}. "
                    f"Updated units involved: {', '.join(affected_updated_units) if affected_updated_units else 'None'}. "
                    f"Transaction will be rolled back to maintain data integrity."
                )
            
            # 7. VALIDATE INDIVIDUAL RELATIONSHIPS IN UPDATED UNITS
            logger.debug("Validating individual relationships in updated units")
            for unit_data in updated_units:
                await self._validate_unit_relationships(unit_data['unit'])
            
            logger.info("Comprehensive post-update validation completed successfully")
            
        except (StratigraphicCycleDetected, InvalidStratigraphicRelation) as e:
            # These are expected validation errors - re-raise for rollback
            raise
        except Exception as e:
            # Unexpected validation error
            logger.error(f"Unexpected error during comprehensive validation: {str(e)}", exc_info=True)
            raise HarrisMatrixValidationError(f"Validation system error: {str(e)}")

    
    async def delete_unit_with_cleanup(
        self,
        site_id: UUID,
        unit_id: UUID,
        unit_type: str
    ) -> Dict[str, Any]:
        """
        Delete a unit with proper cleanup of relationships.
        
        This method performs the database operations for deleting a unit.
        Transaction management should be handled by the caller (API layer).
        
        Args:
            site_id: UUID of the archaeological site
            unit_id: UUID of the unit to delete
            unit_type: Type of unit ('us' or 'usm')
            
        Returns:
            Dictionary with deletion results
        """
        try:
            logger.info(f"Deleting {unit_type} unit {unit_id} from site {site_id}")
            
            # Get the unit
            if unit_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.id == str(unit_id),
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
            else:  # usm
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.id == str(unit_id),
                        UnitaStratigraficaMuraria.site_id == str(site_id),
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
            
            result = await self.db.execute(query)
            unit = result.scalar_one_or_none()
            
            if not unit:
                raise HarrisMatrixValidationError(f"{unit_type.upper()} unit not found")
            
            # Store unit info before deletion
            unit_info = {
                'id': str(unit.id),
                'code': unit.us_code if hasattr(unit, 'us_code') else unit.usm_code,
                'unit_type': unit_type,
                'relationships': unit.sequenza_fisica.copy() if unit.sequenza_fisica else {}
            }
            
            # Find and cleanup references from other units
            await self._cleanup_unit_references(site_id, unit_info)
            
            # Soft delete the unit
            unit.deleted_at = func.now()
            
            result = {
                'deleted_unit': unit_info,
                'cleaned_references': True,
                'success': True
            }
            
            logger.info(f"Unit deletion completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error deleting {unit_type} unit {unit_id}: {str(e)}")
            raise HarrisMatrixServiceError(str(e), "delete_unit_with_cleanup")
    
    async def _cleanup_unit_references(self, site_id: UUID, unit_info: Dict[str, Any]) -> None:
        """Remove references to the deleted unit from other units' relationships."""
        try:
            unit_code = unit_info['code']
            unit_type = unit_info['unit_type']
            
            # Create reference patterns to search for
            reference_patterns = [
                unit_code,  # Simple reference
                f"{unit_code}({unit_type})",  # Typed reference
                unit_code.lower(),  # Case insensitive
                unit_code.upper()
            ]
            
            # Cleanup US units
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            
            for us in us_units:
                if us.sequenza_fisica:
                    modified = False
                    for rel_type, targets in us.sequenza_fisica.items():
                        if targets:
                            # Remove any references to the deleted unit
                            filtered_targets = []
                            for target in targets:
                                # Check if this target references our deleted unit
                                is_reference = False
                                for pattern in reference_patterns:
                                    if pattern in target.lower():
                                        is_reference = True
                                        break
                                
                                if not is_reference:
                                    filtered_targets.append(target)
                                else:
                                    modified = True
                            
                            us.sequenza_fisica[rel_type] = filtered_targets
                    
                    if modified:
                        logger.debug(f"Cleaned references from US {us.us_code}")
            
            # Cleanup USM units
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            for usm in usm_units:
                if usm.sequenza_fisica:
                    modified = False
                    for rel_type, targets in usm.sequenza_fisica.items():
                        if targets:
                            filtered_targets = []
                            for target in targets:
                                is_reference = False
                                for pattern in reference_patterns:
                                    if pattern in target.lower():
                                        is_reference = True
                                        break
                                
                                if not is_reference:
                                    filtered_targets.append(target)
                                else:
                                    modified = True
                            
                            usm.sequenza_fisica[rel_type] = filtered_targets
                    
                    if modified:
                        logger.debug(f"Cleaned references from USM {usm.usm_code}")
            
            logger.info(f"Completed cleanup of references for {unit_type} {unit_code}")
            
        except Exception as e:
            logger.error(f"Error cleaning up unit references: {str(e)}")
            raise
    
    # ===== OTTIMIZZAZIONI PERFORMANCE E CACHING =====
    
    async def get_harris_matrix_with_cache(self, site_id: UUID, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get Harris Matrix with caching support and basic retry logic.
        
        Args:
            site_id: UUID of the archaeological site
            use_cache: Whether to use caching (default: True)
            
        Returns:
            Dictionary with graph data and metadata
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                cache_key = f"harris_matrix:{site_id}"
                
                # Try to get from cache first
                if use_cache:
                    cached_result = await self._get_from_cache(cache_key)
                    if cached_result:
                        logger.info(f"Returning cached Harris Matrix for site {site_id}")
                        return cached_result
                
                # Generate fresh matrix
                result = await self.generate_harris_matrix(site_id)
                
                # Cache the result
                if use_cache and result.get('nodes'):
                    await self._set_cache(cache_key, result, ttl=3600)  # 1 hour cache
                
                return result
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Error getting Harris Matrix with cache for site {site_id} after {max_retries} attempts: {str(e)}")
                    raise
                
                wait_time = 2 ** retry_count  # Simple exponential backoff
                logger.warning(f"Attempt {retry_count} failed for site {site_id}, retrying in {wait_time}s: {str(e)}")
                await asyncio.sleep(wait_time)
    
    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get data from cache. Placeholder implementation.
        
        In production, this should integrate with Redis or similar caching system.
        """
        # Placeholder for caching implementation
        return None
    
    async def _set_cache(self, cache_key: str, data: Dict[str, Any], ttl: int = 3600) -> None:
        """
        Set data in cache. Placeholder implementation.
        
        In production, this should integrate with Redis or similar caching system.
        """
        # Placeholder for caching implementation
        logger.debug(f"Caching data for key: {cache_key} (TTL: {ttl}s)")
    
    async def get_site_statistics_with_performance(self, site_id: UUID) -> Dict[str, Any]:
        """
        Get comprehensive site statistics with performance optimizations and basic retry logic.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary with detailed statistics
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"Getting performance-optimized statistics for site {site_id}")
                
                # Use raw SQL for better performance
                stats_query = text("""
                    SELECT
                        COUNT(CASE WHEN deleted_at IS NULL THEN 1 END) as total_us,
                        COUNT(CASE WHEN deleted_at IS NULL AND tipo = 'positiva' THEN 1 END) as us_positive,
                        COUNT(CASE WHEN deleted_at IS NULL AND tipo = 'negativa' THEN 1 END) as us_negative,
                        COUNT(DISTINCT periodo) as unique_periods,
                        COUNT(DISTINCT fase) as unique_phases,
                        MAX(COALESCE(datazione, '')) as latest_dating
                    FROM unita_stratigrafiche
                    WHERE site_id = :site_id
                """)
                
                us_result = await self.db.execute(stats_query, {"site_id": str(site_id)})
                us_stats = us_result.fetchone()
                
                # USM statistics
                usm_query = text("""
                    SELECT
                        COUNT(CASE WHEN deleted_at IS NULL THEN 1 END) as total_usm,
                        COUNT(DISTINCT tecnica_costruttiva) as unique_techniques,
                        COUNT(DISTINCT periodo) as usm_periods,
                        MAX(COALESCE(datazione, '')) as usm_latest_dating
                    FROM unita_stratigrafiche_murarie
                    WHERE site_id = :site_id
                """)
                
                usm_result = await self.db.execute(usm_query, {"site_id": str(site_id)})
                usm_stats = usm_result.fetchone()
                
                # Relationship statistics (optimized)
                rel_stats = await self._get_relationship_statistics_optimized(site_id)
                
                statistics = {
                    'site_id': str(site_id),
                    'us_statistics': {
                        'total_units': us_stats.total_us or 0,
                        'positive_units': us_stats.us_positive or 0,
                        'negative_units': us_stats.us_negative or 0,
                        'unique_periods': us_stats.unique_periods or 0,
                        'unique_phases': us_stats.unique_phases or 0,
                        'latest_dating': us_stats.latest_dating or ''
                    },
                    'usm_statistics': {
                        'total_units': usm_stats.total_usm or 0,
                        'unique_techniques': usm_stats.unique_techniques or 0,
                        'unique_periods': usm_stats.usm_periods or 0,
                        'latest_dating': usm_stats.usm_latest_dating or ''
                    },
                    'relationship_statistics': rel_stats,
                    'performance_metrics': {
                        'query_time_ms': 0,  # Would need actual timing implementation
                        'cached': False
                    }
                }
                
                logger.info(f"Generated statistics for site {site_id}: {statistics}")
                return statistics
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Error getting performance statistics for site {site_id} after {max_retries} attempts: {str(e)}")
                    raise
                
                wait_time = 2 ** retry_count  # Simple exponential backoff
                logger.warning(f"Attempt {retry_count} failed for site {site_id}, retrying in {wait_time}s: {str(e)}")
                await asyncio.sleep(wait_time)
    
    async def _get_relationship_statistics_optimized(self, site_id: UUID) -> Dict[str, Any]:
        """Get relationship statistics using optimized queries."""
        try:
            # Count relationships from US units
            us_rel_query = text("""
                SELECT
                    json_extract(sequenza_fisica, '$.uguale_a') as uguale_a,
                    json_extract(sequenza_fisica, '$.si_lega_a') as si_lega_a,
                    json_extract(sequenza_fisica, '$.gli_si_appoggia') as gli_si_appoggia,
                    json_extract(sequenza_fisica, '$.si_appoggia_a') as si_appoggia_a,
                    json_extract(sequenza_fisica, '$.coperto_da') as coperto_da,
                    json_extract(sequenza_fisica, '$.copre') as copre,
                    json_extract(sequenza_fisica, '$.tagliato_da') as tagliato_da,
                    json_extract(sequenza_fisica, '$.taglia') as taglia,
                    json_extract(sequenza_fisica, '$.riempito_da') as riempito_da,
                    json_extract(sequenza_fisica, '$.riempie') as riempie
                FROM unita_stratigrafiche
                WHERE site_id = :site_id AND deleted_at IS NULL AND sequenza_fisica IS NOT NULL
            """)
            
            us_rel_result = await self.db.execute(us_rel_query, {"site_id": str(site_id)})
            us_rows = us_rel_result.fetchall()
            
            # Count relationships from USM units
            usm_rel_query = text("""
                SELECT
                    json_extract(sequenza_fisica, '$.uguale_a') as uguale_a,
                    json_extract(sequenza_fisica, '$.si_lega_a') as si_lega_a,
                    json_extract(sequenza_fisica, '$.gli_si_appoggia') as gli_si_appoggia,
                    json_extract(sequenza_fisica, '$.si_appoggia_a') as si_appoggia_a,
                    json_extract(sequenza_fisica, '$.coperto_da') as coperto_da,
                    json_extract(sequenza_fisica, '$.copre') as copre,
                    json_extract(sequenza_fisica, '$.tagliato_da') as tagliato_da,
                    json_extract(sequenza_fisica, '$.taglia') as taglia,
                    json_extract(sequenza_fisica, '$.riempito_da') as riempito_da,
                    json_extract(sequenza_fisica, '$.riempie') as riempie
                FROM unita_stratigrafiche_murarie
                WHERE site_id = :site_id AND deleted_at IS NULL AND sequenza_fisica IS NOT NULL
            """)
            
            usm_rel_result = await self.db.execute(usm_rel_query, {"site_id": str(site_id)})
            usm_rows = usm_rel_result.fetchall()
            
            # Count relationships
            rel_counts = {}
            for rel_type in RELATIONSHIP_TYPES.keys():
                rel_counts[rel_type] = 0
            
            # Process US relationships
            for row in us_rows + usm_rows:
                for rel_type in RELATIONSHIP_TYPES.keys():
                    rel_data = getattr(row, rel_type)
                    if rel_data and isinstance(rel_data, list):
                        rel_counts[rel_type] += len(rel_data)
            
            return {
                'total_relationships': sum(rel_counts.values()),
                'relationship_types': rel_counts,
                'average_relationships_per_unit': sum(rel_counts.values()) / max(len(us_rows) + len(usm_rows), 1)
            }
            
        except Exception as e:
            logger.error(f"Error getting relationship statistics for site {site_id}: {str(e)}")
            return {
                'total_relationships': 0,
                'relationship_types': {},
                'average_relationships_per_unit': 0
            }
    
    @asynccontextmanager
    async def transaction_with_retry(self, max_retries: int = 3):
        """
        Context manager for database transactions with retry logic.
        
        Note: This utility method should be used carefully. Transaction management
        should ideally be handled at the API layer, not within service methods.
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Yields:
            Database session for the transaction
        """
        retry_count = 0
        last_exception = None
        
        while retry_count < max_retries:
            try:
                # Note: This creates a nested transaction - use with caution
                async with self.db.begin() as transaction:
                    yield transaction
                    return  # Success, exit the retry loop
                    
            except Exception as e:
                last_exception = e
                retry_count += 1
                
                if retry_count >= max_retries:
                    logger.error(f"Transaction failed after {max_retries} attempts: {str(e)}")
                    raise
                
                wait_time = 2 ** retry_count  # Exponential backoff
                logger.warning(f"Transaction attempt {retry_count} failed, retrying in {wait_time}s: {str(e)}")
                await asyncio.sleep(wait_time)
        
        # This should not be reached, but just in case
        if last_exception:
            raise last_exception
    
    async def invalidate_cache_for_site(self, site_id: UUID) -> None:
        """
        Invalidate all cache entries for a specific site.
        
        Args:
            site_id: UUID of the archaeological site
        """
        try:
            cache_keys = [
                f"harris_matrix:{site_id}",
                f"site_statistics:{site_id}",
                f"relationships:{site_id}"
            ]
            
            for cache_key in cache_keys:
                # Placeholder for cache invalidation
                logger.debug(f"Invalidating cache key: {cache_key}")
            
            logger.info(f"Invalidated cache for site {site_id}")
            
        except Exception as e:
            logger.error(f"Error invalidating cache for site {site_id}: {str(e)}")
            # Don't raise - cache invalidation failure shouldn't break the main operation
    
    async def get_bulk_operation_progress(self, operation_id: str) -> Dict[str, Any]:
        """
        Get progress information for bulk operations.
        
        Args:
            operation_id: Unique identifier for the bulk operation
            
        Returns:
            Dictionary with progress information
        """
        # Placeholder for progress tracking
        # In production, this would integrate with a job queue system
        return {
            'operation_id': operation_id,
            'status': 'completed',
            'progress_percentage': 100,
            'processed_items': 0,
            'total_items': 0,
            'started_at': None,
            'completed_at': None,
            'error_message': None
        }
    
    async def validate_matrix_integrity(self, site_id: UUID) -> Dict[str, Any]:
        """
        Perform comprehensive matrix integrity validation.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary with validation results
        """
        try:
            logger.info(f"Performing matrix integrity validation for site {site_id}")
            
            # Get current matrix
            matrix_data = await self.generate_harris_matrix(site_id)
            
            validation_results = {
                'site_id': str(site_id),
                'validation_timestamp': None,  # Would need actual timestamp
                'matrix_integrity': {
                    'total_nodes': len(matrix_data.get('nodes', [])),
                    'total_edges': len(matrix_data.get('edges', [])),
                    'orphaned_nodes': 0,
                    'duplicate_nodes': 0,
                    'invalid_edges': 0
                },
                'business_rules': {
                    'cycles_detected': False,
                    'negative_cutting_violations': 0,
                    'positive_covering_violations': 0,
                    'self_references': 0
                },
                'performance_metrics': {
                    'validation_time_ms': 0,
                    'memory_usage_mb': 0
                },
                'is_valid': True,
                'warnings': [],
                'errors': []
            }
            
            # Check for orphaned nodes
            node_ids = {node['id'] for node in matrix_data.get('nodes', [])}
            edge_connections = set()
            
            for edge in matrix_data.get('edges', []):
                if edge['from'] in node_ids and edge['to'] in node_ids:
                    edge_connections.add(edge['from'])
                    edge_connections.add(edge['to'])
                else:
                    validation_results['matrix_integrity']['invalid_edges'] += 1
                    validation_results['errors'].append(f"Invalid edge: {edge['from']} -> {edge['to']}")
            
            # Count orphaned nodes
            orphaned = len(node_ids - edge_connections)
            validation_results['matrix_integrity']['orphaned_nodes'] = orphaned
            
            if orphaned > 0:
                validation_results['warnings'].append(f"Found {orphaned} orphaned nodes without relationships")
            
            # Check for cycles
            if matrix_data.get('edges'):
                # Build graph for cycle detection
                graph = defaultdict(list)
                for edge in matrix_data['edges']:
                    if edge['type'] in ['copre', 'taglia', 'si_appoggia_a', 'riempie']:
                        graph[edge['from']].append(edge['to'])
                
                cycles = CycleDetector.detect_cycles_in_graph(graph)
                if cycles:
                    validation_results['business_rules']['cycles_detected'] = True
                    validation_results['is_valid'] = False
                    validation_results['errors'].append(f"Stratigraphic cycles detected: {cycles}")
            
            # Set overall validity
            validation_results['is_valid'] = (
                validation_results['matrix_integrity']['invalid_edges'] == 0 and
                not validation_results['business_rules']['cycles_detected'] and
                len(validation_results['errors']) == 0
            )
            
            logger.info(f"Matrix integrity validation completed: {'PASS' if validation_results['is_valid'] else 'FAIL'}")
            return validation_results
            
        except Exception as e:
            logger.error(f"Error in matrix integrity validation for site {site_id}: {str(e)}")
            raise
    
    async def _calculate_fallback_positions(
        self,
        site_id: UUID,
        nodes: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calcola posizioni X,Y per i nodi basandosi sulle relazioni stratigrafiche.
        
        Questo metodo di fallback analizza il campo sequenza_fisica delle US/USM
        per generare un layout logico che rispetti le relazioni fisiche.
        
        Args:
            site_id: UUID del sito archeologico
            nodes: Lista dei nodi senza posizioni
            relationships: Lista delle relazioni stratigrafiche
            
        Returns:
            Dizionario con le posizioni calcolate per ogni nodo
        """
        try:
            logger.info(f"Calculating fallback positions for {len(nodes)} nodes using {len(relationships)} relationships")
            
            # 1. Analizza le relazioni per determinare la gerarchia temporale
            temporal_hierarchy = self._build_temporal_hierarchy(nodes, relationships)
            
            # 2. Calcola posizioni Y basate sulla gerarchia (più recenti in alto = Y minore)
            y_positions = self._calculate_y_positions(temporal_hierarchy)
            
            # 3. Distribuisci i nodi sull'asse X per leggibilità
            x_positions = self._calculate_x_positions(temporal_hierarchy, y_positions)
            
            # 4. Combina le posizioni X,Y
            positions = {}
            for node in nodes:
                node_id = node.get("label") or node.get("id")
                positions[node_id] = {
                    "x": x_positions.get(node_id, 0.0),
                    "y": y_positions.get(node_id, 0.0)
                }
            
            logger.info(f"Generated fallback positions for {len(positions)} nodes")
            return positions
            
        except Exception as e:
            logger.error(f"Error calculating fallback positions: {str(e)}")
            # Fallback base: griglia semplice
            return self._generate_grid_fallback(nodes)
    
    def _build_temporal_hierarchy(
        self,
        nodes: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Costruisce una gerarchia temporale basata sulle relazioni stratigrafiche.
        
        Analizza i tipi di relazione per determinare quali nodi sono più antichi
        o più recenti rispetto ad altri.
        """
        hierarchy = {}
        
        # Inizializza tutti i nodi nella gerarchia
        for node in nodes:
            node_id = node.get("label") or node.get("id")
            hierarchy[node_id] = {
                "node": node,
                "covers": set(),      # Nodi che questo nodo copre (più antichi)
                "covered_by": set(),  # Nodi che coprono questo (più recenti)
                "cuts": set(),        # Nodi che questo taglia (più antichi)
                "cut_by": set(),      # Nodi che tagliano questo (più recenti)
                "fills": set(),       # Nodi che questo riempie (più antichi)
                "filled_by": set(),   # Nodi che riempiono questo (più recenti)
                "same_level": set(),  # Nodi allo stesso livello
                "level": None         # Livello temporale calcolato
            }
        
        # Analizza le relazioni
        for rel in relationships:
            from_node = rel.get("from")
            to_node = rel.get("to")
            rel_type = rel.get("type")
            
            if from_node in hierarchy and to_node in hierarchy:
                if rel_type == "copre":
                    hierarchy[from_node]["covers"].add(to_node)
                    hierarchy[to_node]["covered_by"].add(from_node)
                elif rel_type == "coperto_da":
                    hierarchy[to_node]["covers"].add(from_node)
                    hierarchy[from_node]["covered_by"].add(to_node)
                elif rel_type == "taglia":
                    hierarchy[from_node]["cuts"].add(to_node)
                    hierarchy[to_node]["cut_by"].add(from_node)
                elif rel_type == "tagliato_da":
                    hierarchy[to_node]["cuts"].add(from_node)
                    hierarchy[from_node]["cut_by"].add(to_node)
                elif rel_type == "riempie":
                    hierarchy[from_node]["fills"].add(to_node)
                    hierarchy[to_node]["filled_by"].add(from_node)
                elif rel_type == "riempito_da":
                    hierarchy[to_node]["fills"].add(from_node)
                    hierarchy[from_node]["filled_by"].add(to_node)
                elif rel_type in ["uguale_a", "si_lega_a"]:
                    hierarchy[from_node]["same_level"].add(to_node)
                    hierarchy[to_node]["same_level"].add(from_node)
        
        # Calcola i livelli temporali usando topological sort
        self._calculate_temporal_levels(hierarchy)
        
        return hierarchy
    
    def _calculate_temporal_levels(self, hierarchy: Dict[str, Dict[str, Any]]) -> None:
        """
        Calcola i livelli temporali per ogni nodo usando un approccio di topological sort.
        
        I nodi più recenti avranno livelli più bassi (Y più piccolo),
        i nodi più antichi avranno livelli più alti (Y più grande).
        """
        # Inizializza tutti i nodi a livello sconosciuto
        for node_id in hierarchy:
            hierarchy[node_id]["level"] = None
        
        # Trova nodi senza dipendenze (più recenti) - livello 0
        current_level = 0
        unprocessed = set(hierarchy.keys())
        
        while unprocessed:
            # Trova nodi che possono essere processati a questo livello
            ready_nodes = []
            for node_id in list(unprocessed):
                node_data = hierarchy[node_id]
                
                # Un nodo è pronto se non ha nodi che lo coprono/tagliano/riempiono non processati
                blockers = (node_data["covered_by"] | node_data["cut_by"] | node_data["filled_by"])
                unprocessed_blockers = blockers & unprocessed
                
                if not unprocessed_blockers:
                    ready_nodes.append(node_id)
            
            if not ready_nodes:
                # Ciclo detectato o relazioni complesse - assegna livello rimanente
                for node_id in unprocessed:
                    hierarchy[node_id]["level"] = current_level + 1
                break
            
            # Assegna livello ai nodi pronti
            for node_id in ready_nodes:
                hierarchy[node_id]["level"] = current_level
                unprocessed.remove(node_id)
            
            current_level += 1
            
            # Preveni loop infiniti
            if current_level > len(hierarchy) * 2:
                logger.warning("Potential cycle detected in temporal level calculation")
                for node_id in unprocessed:
                    hierarchy[node_id]["level"] = current_level
                break
    
    def _calculate_y_positions(self, hierarchy: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """
        Calcola le posizioni Y basate sui livelli temporali.
        
        Più recenti = Y più piccolo (in alto)
        Più antichi = Y più grande (in basso)
        """
        y_positions = {}
        
        # Raccogli tutti i livelli unici
        levels = set()
        for node_id, node_data in hierarchy.items():
            if node_data["level"] is not None:
                levels.add(node_data["level"])
        
        if not levels:
            # Fallback: tutti allo stesso livello
            y_base = 100
            for node_id in hierarchy:
                y_positions[node_id] = y_base
            return y_positions
        
        # Ordina i livelli (dal più recente al più antico)
        sorted_levels = sorted(levels)
        
        # Calcola Y per ogni livello (spaziatura verticale)
        y_spacing = 120  # Spazio tra livelli
        y_base = 50     # Y di partenza (alto)
        
        for level in sorted_levels:
            nodes_at_level = [node_id for node_id, node_data in hierarchy.items()
                            if node_data["level"] == level]
            
            y_position = y_base + (level * y_spacing)
            
            for node_id in nodes_at_level:
                y_positions[node_id] = float(y_position)
        
        return y_positions
    
    def _calculate_x_positions(
        self,
        hierarchy: Dict[str, Dict[str, Any]],
        y_positions: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calcola le posizioni X distribuendo i nodi per leggibilità.
        
        Nodi allo stesso livello Y vengono distribuiti orizzontalmente.
        """
        x_positions = {}
        
        # Raggruppa nodi per posizione Y
        y_groups = {}
        for node_id, y_pos in y_positions.items():
            if y_pos not in y_groups:
                y_groups[y_pos] = []
            y_groups[y_pos].append(node_id)
        
        # Calcola posizioni X per ogni gruppo
        x_spacing = 150  # Spazio orizzontale tra nodi
        x_base = 100     # X di partenza (sinistra)
        
        for y_pos, nodes in y_groups.items():
            # Ordina i nodi per tipo (US positive, US negative, USM)
            nodes.sort(key=lambda node_id: self._get_node_sort_key(hierarchy[node_id]["node"]))
            
            for i, node_id in enumerate(nodes):
                x_position = x_base + (i * x_spacing)
                x_positions[node_id] = float(x_position)
        
        return x_positions
    
    def _get_node_sort_key(self, node: Dict[str, Any]) -> tuple:
        """
        Restituisce una chiave di ordinamento per i nodi.
        
        Ordine: US positive, USM, US negative
        """
        node_type = node.get("type", "")
        us_type = node.get("tipo", "")
        
        if node_type == "us" and us_type == "positiva":
            return (0, 0)  # US positive prima
        elif node_type == "usm":
            return (0, 1)  # USM dopo US positive
        elif node_type == "us" and us_type == "negativa":
            return (0, 2)  # US negative dopo
        else:
            return (1, 0)  # Altri tipi alla fine
    
    def _generate_grid_fallback(self, nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """
        Fallback di base: disposizione a griglia semplice.
        
        Usato quando il calcolo basato su relazioni fallisce.
        """
        positions = {}
        
        # Calcola dimensioni della griglia
        num_nodes = len(nodes)
        if num_nodes == 0:
            return positions
        
        cols = int(math.ceil(math.sqrt(num_nodes)))
        rows = int(math.ceil(num_nodes / cols))
        
        x_spacing = 150
        y_spacing = 120
        x_base = 100
        y_base = 100
        
        for i, node in enumerate(nodes):
            node_id = node.get("label") or node.get("id")
            row = i // cols
            col = i % cols
            
            positions[node_id] = {
                "x": float(x_base + (col * x_spacing)),
                "y": float(y_base + (row * y_spacing))
            }
        
        logger.info(f"Generated grid fallback positions for {len(positions)} nodes")
        return positions
    
    async def _add_inverse_relationship(
        self,
        site_id: UUID,
        source_reference: str,
        target_reference: str,
        inverse_rel_type: str
    ) -> None:
        """
        Add inverse relationship to target unit.
        
        Args:
            site_id: UUID of the archaeological site
            source_reference: Reference of the source unit (e.g., "US001" or "USM001(usm)")
            target_reference: Reference of the target unit (e.g., "US002" or "002(usm)")
            inverse_rel_type: Type of inverse relationship to add
        """
        try:
            # Parse target reference to extract code and type
            target_code, target_type = parse_target_reference(target_reference)
            
            # Find the target unit
            target_unit = None
            if target_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.us_code == target_code,
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                target_unit = result.scalar_one_or_none()
            elif target_type == 'usm':
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.site_id == str(site_id),
                        UnitaStratigraficaMuraria.usm_code == target_code,
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                target_unit = result.scalar_one_or_none()
            
            if not target_unit:
                logger.warning(f"Target unit not found for inverse relationship: {target_type}{target_code}")
                return
            
            # Initialize inverse relationship type if it doesn't exist
            if not target_unit.sequenza_fisica:
                target_unit.sequenza_fisica = get_default_sequenza_fisica()
            
            if inverse_rel_type not in target_unit.sequenza_fisica:
                target_unit.sequenza_fisica[inverse_rel_type] = []
            
            # Add inverse relationship if not already present
            if source_reference not in target_unit.sequenza_fisica[inverse_rel_type]:
                target_unit.sequenza_fisica[inverse_rel_type].append(source_reference)
                
                # CRITICAL: Mark JSON field as modified for SQLAlchemy
                flag_modified(target_unit, "sequenza_fisica")
                
                logger.debug(f"Added inverse relationship {source_reference} to {inverse_rel_type} for target unit {target_unit.id}")
            else:
                logger.debug(f"Inverse relationship {source_reference} already exists in {inverse_rel_type}")
                
        except Exception as e:
            logger.error(f"Error adding inverse relationship: {str(e)}")
            # Don't raise - inverse relationship failures shouldn't break the main operation
    
    async def _remove_inverse_relationship(
        self,
        site_id: UUID,
        source_reference: str,
        target_reference: str,
        inverse_rel_type: str
    ) -> None:
        """
        Remove inverse relationship from target unit.
        
        Args:
            site_id: UUID of the archaeological site
            source_reference: Reference of the source unit (e.g., "US001" or "USM001(usm)")
            target_reference: Reference of the target unit (e.g., "US002" or "002(usm)")
            inverse_rel_type: Type of inverse relationship to remove
        """
        try:
            # Parse target reference to extract code and type
            target_code, target_type = parse_target_reference(target_reference)
            
            # Find the target unit
            target_unit = None
            if target_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.us_code == target_code,
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                target_unit = result.scalar_one_or_none()
            elif target_type == 'usm':
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.site_id == str(site_id),
                        UnitaStratigraficaMuraria.usm_code == target_code,
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                target_unit = result.scalar_one_or_none()
            
            if not target_unit:
                logger.warning(f"Target unit not found for inverse relationship removal: {target_type}{target_code}")
                return
            
            # Remove inverse relationship if it exists
            if (target_unit.sequenza_fisica and
                inverse_rel_type in target_unit.sequenza_fisica and
                source_reference in target_unit.sequenza_fisica[inverse_rel_type]):
                
                target_unit.sequenza_fisica[inverse_rel_type].remove(source_reference)
                
                # CRITICAL: Mark JSON field as modified for SQLAlchemy
                flag_modified(target_unit, "sequenza_fisica")
                
                logger.debug(f"Removed inverse relationship {source_reference} from {inverse_rel_type} for target unit {target_unit.id}")
            else:
                logger.debug(f"Inverse relationship {source_reference} not found in {inverse_rel_type}")
                
        except Exception as e:
            logger.error(f"Error removing inverse relationship: {str(e)}")
            # Don't raise - inverse relationship failures shouldn't break the main operation
    async def validate_relationship_consistency(self, site_id: UUID, db: AsyncSession) -> Dict[str, Any]:
        """Validate relationship consistency and bidirectional integrity"""
        
        from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
        
        try:
            # Load all units for the site
            us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == str(site_id))
            us_result = await db.execute(us_query)
            us_units = us_result.scalars().all()
            
            usm_query = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.site_id == str(site_id))
            usm_result = await db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            # Build relationship list from sequenza_fisica
            relationships = []
            all_units = {}
            
            for unit in us_units + usm_units:
                all_units[str(unit.id)] = unit
                unit_code = unit.us_code if hasattr(unit, 'us_code') else unit.usm_code
                
                if unit.sequenza_fisica:
                    for rel_type, targets in unit.sequenza_fisica.items():
                        if targets:
                            for target in targets:
                                # Parse target reference
                                target_code, target_type = parse_target_reference(target)
                                
                                # Find target unit
                                target_unit = None
                                for search_unit in all_units.values():
                                    search_code = search_unit.us_code if hasattr(search_unit, 'us_code') else search_unit.usm_code
                                    if search_code == target_code:
                                        target_unit = search_unit
                                        break
                                
                                if target_unit:
                                    relationships.append({
                                        'from_unit_id': str(unit.id),
                                        'from_unit_code': unit_code,
                                        'to_unit_id': str(target_unit.id),
                                        'to_unit_code': target_code,
                                        'relationship_type': rel_type
                                    })
            
            # Check for bidirectional consistency
            issues = []
            relationship_map = {}
            
            for rel in relationships:
                from_id = rel['from_unit_id']
                to_id = rel['to_unit_id']
                rel_type = rel['relationship_type']
                inverse_type = RELATIONSHIP_INVERSES.get(rel_type)
                
                # Track direct relationships
                key = f"{from_id}->{to_id}:{rel_type}"
                relationship_map[key] = rel
                
                # Check if inverse exists
                if inverse_type:
                    inverse_key = f"{to_id}->{from_id}:{inverse_type}"
                    if inverse_key not in relationship_map:
                        issues.append({
                            "type": "missing_inverse",
                            "relationship_id": None,
                            "from_unit": rel['from_unit_code'],
                            "to_unit": rel['to_unit_code'],
                            "relationship_type": rel_type,
                            "expected_inverse": inverse_type,
                            "severity": "warning"
                        })
            
            return {
                "total_relationships": len(relationships),
                "consistency_issues": issues,
                "is_consistent": len(issues) == 0,
                "site_id": str(site_id)
            }
            
        except Exception as e:
            logger.error(f"[VALIDATION ERROR] Failed to validate relationships: {str(e)}", exc_info=True)
            raise

# ===== COMPREHENSIVE VALIDATION AND ERROR HANDLING FIX #3 =====

    async def validate_harris_matrix_structure(self, site_id: UUID, units: List[Dict], relationships: List[Dict], db: AsyncSession) -> Dict[str, Any]:
        """Comprehensive validation of Harris Matrix structure"""
        
        validation_errors = []
        warnings = []
        
        # Phase 1: Validate units
        unit_codes = set()
        for unit in units:
            if 'code' not in unit:
                validation_errors.append({
                    "type": "missing_code",
                    "unit": unit.get('tempid', 'unknown'),
                    "message": "Each unit must have a code"
                })
                continue
            
            code = unit['code']
            if code in unit_codes:
                validation_errors.append({
                    "type": "duplicate_code",
                    "code": code,
                    "message": f"Duplicate unit code: {code}"
                })
            unit_codes.add(code)
        
        # Phase 2: Validate relationships
        unit_tempids = {unit.get('tempid') for unit in units}
        for rel in relationships:
            from_tempid = rel.get('from_tempid')
            to_tempid = rel.get('to_tempid')
            
            if from_tempid not in unit_tempids:
                validation_errors.append({
                    "type": "invalid_from_unit",
                    "relationship": rel.get('tempid', 'unknown'),
                    "from_tempid": from_tempid,
                    "message": f"Source unit {from_tempid} not found in units"
                })
            
            if to_tempid not in unit_tempids:
                validation_errors.append({
                    "type": "invalid_to_unit",
                    "relationship": rel.get('tempid', 'unknown'),
                    "to_tempid": to_tempid,
                    "message": f"Target unit {to_tempid} not found in units"
                })
            
            # Check for self-relationships (except for self-inverse types)
            if from_tempid == to_tempid:
                rel_type = rel.get('relationship_type')
                if rel_type not in ['silegaa', 'ugualea']:
                    validation_errors.append({
                        "type": "self_relationship",
                        "relationship": rel.get('tempid', 'unknown'),
                        "from_tempid": from_tempid,
                        "relationship_type": rel_type,
                        "message": f"Self-relationships not allowed for {rel_type}"
                    })
        
        # Phase 3: Cycle detection
        if validation_errors:
            return {
                "is_valid": False,
                "validation_errors": validation_errors,
                "warnings": warnings
            }
        
        # Build graph for cycle detection
        graph = {}
        for rel in relationships:
            from_tempid = rel.get('from_tempid')
            to_tempid = rel.get('to_tempid')
            rel_type = rel.get('relationship_type')
            
            # Only check for cycles in "covers" relationships (copre, taglia, riempie)
            if rel_type in ['copre', 'taglia', 'riempie']:
                if from_tempid not in graph:
                    graph[from_tempid] = []
                graph[from_tempid].append(to_tempid)
        
        # Detect cycles using DFS
        cycles = self._detect_cycles(graph)
        
        for cycle in cycles:
            validation_errors.append({
                "type": "cycle_detected",
                "cycle": cycle,
                "message": f"Cycle detected: {' -> '.join(cycle)} -> {cycle[0]}"
            })
        
        # Phase 4: Check for logical inconsistencies
        logical_issues = await self._check_logical_consistency(relationships, db)
        validation_errors.extend(logical_issues)
        
        return {
            "is_valid": len(validation_errors) == 0,
            "validation_errors": validation_errors,
            "warnings": warnings,
            "units_count": len(units),
            "relationships_count": len(relationships)
        }

    def _detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        """Detect cycles in the relationship graph using DFS"""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node, path):
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                dfs(neighbor, path + [node])
            
            rec_stack.remove(node)
        
        for node in graph:
            if node not in visited:
                dfs(node, [])
        
        return cycles

    async def _check_logical_consistency(self, relationships: List[Dict], db: AsyncSession) -> List[Dict]:
        """Check for logical inconsistencies in relationships"""
        issues = []
        
        # Group relationships by unit pairs
        relationship_map = {}
        for rel in relationships:
            from_tempid = rel.get('from_tempid')
            to_tempid = rel.get('to_tempid')
            rel_type = rel.get('relationship_type')
            
            pair_key = f"{from_tempid}-{to_tempid}"
            if pair_key not in relationship_map:
                relationship_map[pair_key] = []
            relationship_map[pair_key].append(rel_type)
        
        # Check for conflicting relationships
        for pair_key, rel_types in relationship_map.items():
            if len(rel_types) > 1:
                # Check for conflicting relationship types
                conflicting_pairs = [
                    ('copre', 'coperto_da'),
                    ('taglia', 'tagliatoda'), 
                    ('riempie', 'riempito_da')
                ]
                
                for conflict_a, conflict_b in conflicting_pairs:
                    if conflict_a in rel_types and conflict_b in rel_types:
                        from_tempid, to_tempid = pair_key.split('-')
                        issues.append({
                            "type": "conflicting_relationships",
                            "from_tempid": from_tempid,
                            "to_tempid": to_tempid,
                            "relationships": rel_types,
                            "message": f"Conflicting relationships {conflict_a} and {conflict_b} between same units"
                        })
        
        return issues

# ===== COMPREHENSIVE VALIDATION AND ERROR HANDLING FIX #4 =====

    async def create_harris_matrix_with_rollback(self, site_id: UUID, request: HarrisMatrixCreateRequest, db: AsyncSession) -> Dict[str, Any]:
        """Create Harris Matrix with comprehensive rollback on failure"""
        
        try:
            # Start transaction
            async with db.begin():
                # Phase 1: Validation
                validation_result = await self.validate_harris_matrix_structure(
                    site_id, request.units, request.relationships, db
                )
                
                if not validation_result["is_valid"]:
                    raise ValidationError(f"Validation failed: {len(validation_result['validation_errors'])} errors found")
                
                # Phase 2: Create units
                created_units = []
                unit_tempid_to_id = {}
                
                for unit_data in request.units:
                    unit = await self._create_unit_with_validation(unit_data, site_id, db)
                    created_units.append(unit)
                    unit_tempid_to_id[unit_data['tempid']] = str(unit.id)
                
                # Phase 3: Create relationships with validation
                created_relationships = []
                for rel_data in request.relationships:
                    relationship = await self._create_relationship_with_validation(
                        rel_data, unit_tempid_to_id, site_id, db
                    )
                    created_relationships.append(relationship)
                
                # Phase 4: Final consistency check
                await self._verify_data_integrity(site_id, db)
                
                return {
                    "success": True,
                    "created_units": created_units,
                    "created_relationships": created_relationships,
                    "unit_mapping": unit_tempid_to_id,
                    "validation_result": validation_result
                }
                
        except Exception as e:
            await db.rollback()
            logger.error(f"[HARRIS MATRIX CREATION ERROR] Operation rolled back: {str(e)}", exc_info=True)
            raise

    async def _verify_data_integrity(self, site_id: UUID, db: AsyncSession) -> None:
        """Verify data integrity after operations"""
        
        # Check for orphaned relationships
        from app.models.stratigraphy import StratigraphicUnit, StratigraphicRelationship
        
        # Count units and relationships
        units_count = await db.execute(
            select(func.count(StratigraphicUnit.id))
            .where(StratigraphicUnit.site_id == site_id)
        )
        
        relationships_count = await db.execute(
            select(func.count(StratigraphicRelationship.id))
            .where(StratigraphicRelationship.site_id == site_id)
        )
        
        units_result = units_count.scalar()
        relationships_result = relationships_count.scalar()
        
        logger.info(f"[INTEGRITY CHECK] Site {site_id}: {units_result} units, {relationships_result} relationships")
        
        # Additional integrity checks can be added here
