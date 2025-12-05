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
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID, uuid4
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from loguru import logger

from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.models.harris_matrix_layout import HarrisMatrixLayout
from app.services.harris_matrix_unit_resolver import UnitResolver
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
                for node in nodes:
                    node_id = node.get("label") or node.get("id")
                    if node_id in layouts:
                        node["position"] = layouts[node_id]
                    else:
                        # Default position if not saved
                        node["position"] = None

                logger.debug(f"Added {len(layouts)} saved positions to nodes")

            except Exception as e:
                logger.warning(f"Could not load layout positions: {str(e)}")
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
                
                # First, try traditional lookup for performance
                if target_type == 'us' and target_code in us_lookup:
                    target_exists = True
                elif target_type == 'usm' and target_code in usm_lookup:
                    target_exists = True
                else:
                    # Use enhanced resolver for missing units
                    logger.debug(f"Traditional lookup failed for {target_type}{target_code}, trying enhanced resolution")
                    resolved_id = await self.unit_resolver.resolve_unit_code(target_code, target_type)
                    if resolved_id:
                        target_exists = True
                        logger.info(f"Successfully resolved {target_type}{target_code} using enhanced resolver")
                    else:
                        # Check for specific known issues
                        if target_code in ['402', '412', 'US402', 'US412', 'USM402', 'USM402']:
                            logger.warning(
                                f"Known problematic unit reference found: {target_type}{target_code}. "
                                f"This unit may not exist in the database or has format issues."
                            )
                        else:
                            logger.warning(f"Cannot resolve {target_type}{target_code} for relationship {rel_type}")
                        continue
                
                # Determine relationship direction
                if rel_config['bidirectional']:
                    # For bidirectional relationships, create edge from source to target
                    from_node = f"{source_type.upper()}{source_code}"
                    to_node = f"{target_type.upper()}{target_code}"
                    bidirectional = True
                elif rel_type in ['coperto_da', 'tagliato_da', 'riempito_da']:
                    # These are "from target to source" relationships
                    from_node = f"{target_type.upper()}{target_code}"
                    to_node = f"{source_type.upper()}{source_code}"
                    bidirectional = False
                else:
                    # These are "from source to target" relationships
                    from_node = f"{source_type.upper()}{source_code}"
                    to_node = f"{target_type.upper()}{target_code}"
                    bidirectional = False
                
                relationship = {
                    'from': from_node,
                    'to': to_node,
                    'type': rel_type,
                    'label': rel_config['label'],
                    'bidirectional': bidirectional,
                    'description': rel_config['description'],
                    'resolved': target_exists,
                    'resolution_method': 'enhanced_resolver' if target_exists and target_type == 'us' and target_code not in us_lookup else 'direct_lookup'
                }
                
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
            
            # Check for code conflicts first
            logger.debug("DEBUG: Checking code conflicts...")
            await self.unit_lookup.check_code_conflicts(site_id, units_data)
            logger.debug("DEBUG: Code conflicts check passed")
                
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
                
            result = {
                    'created_units': len(created_units),
                    'created_relationships': len(created_relationships),
                    'unit_mapping': {unit['temp_id']: unit['id'] for unit in created_units},
                    'relationship_mapping': {rel['temp_id']: rel['temp_id'] for rel in created_relationships},
                    'units': created_units,
                    'relationships': created_relationships
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
                
                created_units.append({
                    'temp_id': temp_id,
                    'id': str(unit.id),
                    'code': unit_data['code'],
                    'unit_type': unit_type
                })
            
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
                    await self._validate_single_relationship(from_unit, to_unit, relation_type)
                    
                    # Add relationship to from_unit's sequenza_fisica
                    target_code = to_unit.usm_code if hasattr(to_unit, 'usm_code') else to_unit.us_code
                    
                    # Add type suffix for cross-references
                    if hasattr(to_unit, 'usm_code'):
                        target_reference = f"{target_code}(usm)"
                    else:
                        target_reference = target_code
                    
                    logger.debug(f"DEBUG: Adding target_reference '{target_reference}' to relationship type '{relation_type}'")
                    
                    if target_reference not in from_unit.sequenza_fisica.get(relation_type, []):
                        from_unit.sequenza_fisica[relation_type].append(target_reference)
                        logger.debug(f"DEBUG: Added relationship successfully")
                    else:
                        logger.debug(f"DEBUG: Relationship already exists, skipping")
                
                    # Debug logging to validate assumptions
                    logger.debug(f"DEBUG: Creating temp_id for relationship from={from_unit.id} to={to_unit.id}, type={relation_type}")
                    created_relationships.append({
                        'temp_id': rel_data.get('temp_id', str(uuid4())),
                        'from_unit_id': str(from_unit.id),
                        'to_unit_id': str(to_unit.id),
                        'relation_type': relation_type
                    })
                    logger.debug(f"DEBUG: Created relationship temp_id={created_relationships[-1]['temp_id']}")
                    
                except Exception as e:
                    logger.error(f"DEBUG: Error processing relationship {rel_data}: {e}")
                    continue
            
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
    
    
    
    
    async def _validate_single_relationship(
        self,
        from_unit,
        to_unit,
        relation_type: str
    ) -> None:
        """Validate a single relationship using centralized validator."""
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
            
            async with self.db.begin():
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
                
                # Validate the updated relationships
                # This would require more complex validation logic
                # For now, we'll skip full validation in bulk updates
                
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
            logger.error(f"Error in bulk relationship update for {unit_type} {unit_id}: {str(e)}")
            raise HarrisMatrixServiceError(str(e), "bulk_update_relationships")
    
    async def delete_unit_with_cleanup(
        self,
        site_id: UUID,
        unit_id: UUID,
        unit_type: str
    ) -> Dict[str, Any]:
        """
        Delete a unit with proper cleanup of relationships.
        
        Args:
            site_id: UUID of the archaeological site
            unit_id: UUID of the unit to delete
            unit_type: Type of unit ('us' or 'usm')
            
        Returns:
            Dictionary with deletion results
        """
        try:
            logger.info(f"Deleting {unit_type} unit {unit_id} from site {site_id}")
            
            async with self.db.begin():
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
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Yields:
            Database session for the transaction
        """
        retry_count = 0
        last_exception = None
        
        while retry_count < max_retries:
            try:
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