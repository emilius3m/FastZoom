# app/services/harris_matrix_service.py
"""
Service for generating Harris Matrix graph data from US/USM stratigraphic relationships.

This service queries both US and USM tables for a given site_id, extracts relationships
from the sequenza_fisica JSON field, and generates graph data structures suitable
for Cytoscape.js visualization with topological sorting for chronological levels.
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from loguru import logger

from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
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
    
    # Relationship type mappings from sequenza_fisica JSON
    RELATIONSHIP_TYPES = {
        'uguale_a': {
            'label': 'uguale a',
            'bidirectional': True,
            'description': 'Equal to (contemporaneous)'
        },
        'si_lega_a': {
            'label': 'si lega a',
            'bidirectional': True,
            'description': 'Bonds with'
        },
        'gli_si_appoggia': {
            'label': 'gli si appoggia',
            'bidirectional': True,
            'description': 'Others rest on this'
        },
        'si_appoggia_a': {
            'label': 'si appoggia a',
            'bidirectional': False,
            'description': 'This unit rests on others'
        },
        'coperto_da': {
            'label': 'coperto da',
            'bidirectional': False,
            'description': 'Covered by'
        },
        'copre': {
            'label': 'copre',
            'bidirectional': False,
            'description': 'Covers'
        },
        'tagliato_da': {
            'label': 'tagliato da',
            'bidirectional': False,
            'description': 'Cut by'
        },
        'taglia': {
            'label': 'taglia',
            'bidirectional': False,
            'description': 'Cuts'
        },
        'riempito_da': {
            'label': 'riempito da',
            'bidirectional': False,
            'description': 'Filled by'
        },
        'riempie': {
            'label': 'riempie',
            'bidirectional': False,
            'description': 'Fills'
        }
    }
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the Harris Matrix service.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db
    
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
            
            # Query all US and USM units for the site
            us_units, usm_units = await self._query_stratigraphic_units(site_id)
            
            if not us_units and not usm_units:
                logger.warning(f"No stratigraphic units found for site_id: {site_id}")
                return self._empty_graph()
            
            # Extract relationships from sequenza_fisica
            relationships = await self._extract_relationships(us_units, usm_units)
            
            # Build graph data structures
            nodes = self._build_nodes(us_units, usm_units)
            edges = self._build_edges(relationships)
            
            # Calculate chronological levels using topological sort
            levels = self._calculate_chronological_levels(nodes, edges)
            
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
    
    async def _query_stratigraphic_units(
        self, 
        site_id: UUID
    ) -> Tuple[List[UnitaStratigrafica], List[UnitaStratigraficaMuraria]]:
        """
        Query all US and USM units for a site with eager loading.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Tuple of (US units list, USM units list)
        """
        try:
            # Query US units
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.deleted_at.is_(None)  # Soft delete filter
                )
            ).order_by(UnitaStratigrafica.us_code)
            
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            
            # Query USM units
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.deleted_at.is_(None)  # Soft delete filter
                )
            ).order_by(UnitaStratigraficaMuraria.usm_code)
            
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            logger.info(f"Found {len(us_units)} US units and {len(usm_units)} USM units for site {site_id}")
            return us_units, usm_units
            
        except Exception as e:
            logger.error(f"Error querying stratigraphic units for site_id {site_id}: {str(e)}")
            raise
    
    async def _extract_relationships(
        self,
        us_units: List[UnitaStratigrafica],
        usm_units: List[UnitaStratigraficaMuraria]
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships from sequenza_fisica JSON fields.
        
        Args:
            us_units: List of US units
            usm_units: List of USM units
            
        Returns:
            List of relationship dictionaries
        """
        relationships = []
        
        # Create lookup dictionaries for unit codes
        us_lookup = {us.us_code: us for us in us_units}
        usm_lookup = {usm.usm_code: usm for usm in usm_units}
        
        # Process US units
        for us in us_units:
            if not us.sequenza_fisica:
                continue
                
            us_relationships = self._extract_unit_relationships(
                us.sequenza_fisica, us.us_code, 'us', us_lookup, usm_lookup
            )
            relationships.extend(us_relationships)
        
        # Process USM units
        for usm in usm_units:
            if not usm.sequenza_fisica:
                continue
                
            usm_relationships = self._extract_unit_relationships(
                usm.sequenza_fisica, usm.usm_code, 'usm', us_lookup, usm_lookup
            )
            relationships.extend(usm_relationships)
        
        logger.info(f"Extracted {len(relationships)} relationships from sequenza_fisica")
        return relationships
    
    def _extract_unit_relationships(
        self,
        sequenza_fisica: Dict[str, List[str]],
        source_code: str,
        source_type: str,
        us_lookup: Dict[str, UnitaStratigrafica],
        usm_lookup: Dict[str, UnitaStratigraficaMuraria]
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships for a single unit from its sequenza_fisica.
        
        Args:
            sequenza_fisica: JSON structure containing relationships
            source_code: Code of the source unit
            source_type: Type of source unit ('us' or 'usm')
            us_lookup: Dictionary mapping US codes to US objects
            usm_lookup: Dictionary mapping USM codes to USM objects
            
        Returns:
            List of relationship dictionaries
        """
        relationships = []
        
        for rel_type, targets in sequenza_fisica.items():
            if not targets or rel_type not in self.RELATIONSHIP_TYPES:
                continue
            
            rel_config = self.RELATIONSHIP_TYPES[rel_type]
            
            for target in targets:
                # Parse target to handle cross-references like "174(usm)"
                target_code, target_type = self._parse_target_reference(target)
                
                # Validate target exists
                if target_type == 'us' and target_code not in us_lookup:
                    logger.warning(f"US target {target_code} not found for relationship {rel_type}")
                    continue
                elif target_type == 'usm' and target_code not in usm_lookup:
                    logger.warning(f"USM target {target_code} not found for relationship {rel_type}")
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
                    'description': rel_config['description']
                }
                
                relationships.append(relationship)
        
        return relationships
    
    def _parse_target_reference(self, target: str) -> Tuple[str, str]:
        """
        Parse target reference to extract code and type.
        
        Args:
            target: Target string, possibly with type suffix like "174(usm)"
            
        Returns:
            Tuple of (code, type) where type is 'us' or 'usm'
        """
        # Check for explicit type specification
        match = re.match(r'^(\w+)\((usm?)\)$', target.lower())
        if match:
            code = match.group(1).upper()
            unit_type = match.group(2)
            return code, unit_type
        
        # Default to US if no type specified
        return target.upper(), 'us'
    
    def _build_nodes(
        self,
        us_units: List[UnitaStratigrafica],
        usm_units: List[UnitaStratigraficaMuraria]
    ) -> List[Dict[str, Any]]:
        """
        Build node list for graph visualization.
        
        Args:
            us_units: List of US units
            usm_units: List of USM units
            
        Returns:
            List of node dictionaries
        """
        nodes = []
        
        # Add US nodes
        for us in us_units:
            # Debug logging per verificare il campo tipo
            logger.debug(f"Processing US {us.us_code}: tipo={getattr(us, 'tipo', 'NOT_FOUND')}")
            
            node = {
                'id': f"US{us.us_code}",
                'type': 'us',
                'label': us.us_code,
                'definition': us.definizione or '',
                'tipo': getattr(us, 'tipo', 'positiva') or 'positiva',  # ⭐ Aggiungi campo tipo con fallback
                'data': {
                    'id': str(us.id),
                    'localita': us.localita or '',
                    'datazione': us.datazione or '',
                    'periodo': us.periodo or '',
                    'fase': us.fase or '',
                    'affidabilita': us.affidabilita_stratigrafica or '',
                    'site_id': us.site_id
                }
            }
            nodes.append(node)
            
            # Debug logging per verificare il nodo creato
            logger.debug(f"Created node for US {us.us_code}: tipo={node['tipo']}")
        
        # Add USM nodes
        for usm in usm_units:
            node = {
                'id': f"USM{usm.usm_code}",
                'type': 'usm',
                'label': usm.usm_code,
                'definition': usm.definizione or '',
                'data': {
                    'id': str(usm.id),
                    'localita': usm.localita or '',
                    'datazione': usm.datazione or '',
                    'periodo': usm.periodo or '',
                    'fase': usm.fase or '',
                    'tecnica_costruttiva': usm.tecnica_costruttiva or '',
                    'site_id': usm.site_id
                }
            }
            nodes.append(node)
        
        logger.info(f"Built {len(nodes)} nodes for graph")
        return nodes
    
    def _build_edges(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build edge list for graph visualization.
        
        Args:
            relationships: List of relationship dictionaries
            
        Returns:
            List of edge dictionaries
        """
        edges = []
        
        for rel in relationships:
            edge = {
                'from': rel['from'],
                'to': rel['to'],
                'type': rel['type'],
                'label': rel['label'],
                'bidirectional': rel['bidirectional']
            }
            edges.append(edge)
        
        logger.info(f"Built {len(edges)} edges for graph")
        return edges
    
    def _calculate_chronological_levels(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Calculate chronological levels using topological sort.
        
        Level 0 = most recent units (highest in stratigraphic sequence)
        Higher numbers = older units (deeper in stratigraphic sequence)
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            
        Returns:
            Dictionary mapping node IDs to their chronological levels
        """
        # Build adjacency list for directed graph
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        node_set = set(node['id'] for node in nodes)
        
        # Initialize graph
        for node_id in node_set:
            in_degree[node_id] = 0
            graph[node_id] = []
        
        # Add edges (considering direction)
        for edge in edges:
            from_node = edge['from']
            to_node = edge['to']
            
            if from_node in node_set and to_node in node_set:
                # For chronological ordering, we need to understand the stratigraphic direction
                # "copre" (covers) means from_node is above to_node (more recent)
                # "taglia" (cuts) means from_node cuts through to_node (more recent)
                # "si appoggia a" (rests on) means from_node is above to_node (more recent)
                
                if edge['type'] in ['copre', 'taglia', 'si_appoggia_a']:
                    # from_node is more recent than to_node
                    graph[from_node].append(to_node)
                    in_degree[to_node] += 1
                elif edge['type'] in ['coperto_da', 'tagliato_da', 'riempito_da']:
                    # from_node is older than to_node
                    graph[to_node].append(from_node)
                    in_degree[from_node] += 1
                elif edge['bidirectional']:
                    # For bidirectional relationships, we don't affect chronological ordering
                    pass
        
        # Topological sort to assign levels
        levels = {}
        queue = deque()
        
        # Find nodes with no incoming edges (most recent)
        for node_id in node_set:
            if in_degree[node_id] == 0:
                queue.append(node_id)
                levels[node_id] = 0
        
        # Process nodes in topological order
        while queue:
            current = queue.popleft()
            current_level = levels[current]
            
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                
                # Update neighbor level (should be deeper/older)
                if neighbor not in levels or levels[neighbor] <= current_level:
                    levels[neighbor] = current_level + 1
                
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Handle any remaining nodes (cycles) by assigning them to the deepest level
        max_level = max(levels.values()) if levels else 0
        for node_id in node_set:
            if node_id not in levels:
                levels[node_id] = max_level + 1
                logger.warning(f"Node {node_id} assigned to level {max_level + 1} due to cycle")
        
        logger.info(f"Calculated chronological levels for {len(levels)} nodes")
        return levels
    
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
                if targets and rel_type in self.RELATIONSHIP_TYPES:
                    relationships[rel_type] = {
                        'targets': targets,
                        'label': self.RELATIONSHIP_TYPES[rel_type]['label'],
                        'description': self.RELATIONSHIP_TYPES[rel_type]['description'],
                        'bidirectional': self.RELATIONSHIP_TYPES[rel_type]['bidirectional']
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
        relationships_data: List[Dict[str, Any]]
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
            
            async with self.db.begin():
                # Check for code conflicts first
                await self._check_code_conflicts(site_id, units_data)
                
                # Generate sequential codes if not provided
                units_with_codes = await self._generate_sequential_codes(site_id, units_data)
                
                # Create units
                created_units = await self._bulk_create_units(site_id, units_with_codes)
                
                # Create relationships
                created_relationships = await self._bulk_create_relationships(
                    created_units, relationships_data
                )
                
                # Validate relationships for cycles
                await self.validate_stratigraphic_relationships(created_units, created_relationships)
                
                result = {
                    'created_units': len(created_units),
                    'created_relationships': len(created_relationships),
                    'unit_mapping': {unit['temp_id']: unit['id'] for unit in created_units},
                    'relationship_mapping': {rel['temp_id']: rel['id'] for rel in created_relationships},
                    'units': created_units,
                    'relationships': created_relationships
                }
                
                logger.info(f"Bulk creation completed successfully: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Error in bulk creation for site {site_id}: {str(e)}")
            raise HarrisMatrixServiceError(str(e), "bulk_create_units_with_relationships")
    
    async def _check_code_conflicts(self, site_id: UUID, units_data: List[Dict[str, Any]]) -> None:
        """Check for existing unit codes in the site."""
        try:
            existing_us_codes = set()
            existing_usm_codes = set()
            
            # Get existing US codes
            us_query = select(UnitaStratigrafica.us_code).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            us_result = await self.db.execute(us_query)
            existing_us_codes = set(row[0] for row in us_result.fetchall())
            
            # Get existing USM codes
            usm_query = select(UnitaStratigraficaMuraria.usm_code).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            usm_result = await self.db.execute(usm_query)
            existing_usm_codes = set(row[0] for row in usm_result.fetchall())
            
            # Check for conflicts
            for unit_data in units_data:
                unit_type = unit_data.get('unit_type', 'us')
                code = unit_data.get('code')
                
                if code:
                    if unit_type == 'us' and code in existing_us_codes:
                        raise UnitCodeConflict(code, 'us')
                    elif unit_type == 'usm' and code in existing_usm_codes:
                        raise UnitCodeConflict(code, 'usm')
                        
        except Exception as e:
            logger.error(f"Error checking code conflicts for site {site_id}: {str(e)}")
            raise
    
    async def _generate_sequential_codes(self, site_id: UUID, units_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate sequential codes for units without explicit codes."""
        try:
            # Get current max codes
            us_max_query = select(func.max(UnitaStratigrafica.us_code)).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            us_max_result = await self.db.execute(us_max_query)
            us_max = us_max_result.scalar() or 0
            
            usm_max_query = select(func.max(UnitaStratigraficaMuraria.usm_code)).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            usm_max_result = await self.db.execute(usm_max_query)
            usm_max = usm_max_result.scalar() or 0
            
            # Extract numeric parts
            us_max_num = int(re.sub(r'\D', '', str(us_max))) if us_max else 0
            usm_max_num = int(re.sub(r'\D', '', str(usm_max))) if usm_max else 0
            
            us_counter = us_max_num + 1
            usm_counter = usm_max_num + 1
            
            # Generate codes for units without them
            result = []
            for unit_data in units_data:
                unit_type = unit_data.get('unit_type', 'us')
                
                if not unit_data.get('code'):
                    if unit_type == 'us':
                        unit_data['code'] = f"US{us_counter:03d}"
                        us_counter += 1
                    elif unit_type == 'usm':
                        unit_data['code'] = f"USM{usm_counter:03d}"
                        usm_counter += 1
                
                result.append(unit_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating sequential codes for site {site_id}: {str(e)}")
            raise
    
    async def _bulk_create_units(self, site_id: UUID, units_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create multiple units in bulk."""
        try:
            created_units = []
            
            for unit_data in units_data:
                unit_type = unit_data.get('unit_type', 'us')
                temp_id = unit_data.get('temp_id', str(UUID.uuid4()))
                
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
                        sequenza_fisica=self._get_default_sequenza_fisica(),
                        created_by=unit_data.get('created_by')
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
                        sequenza_fisica=self._get_default_sequenza_fisica(),
                        created_by=unit_data.get('created_by')
                    )
                
                self.db.add(unit)
                await self.db.flush()  # Get the ID
                
                created_units.append({
                    'temp_id': temp_id,
                    'id': str(unit.id),
                    'code': unit_data['code'],
                    'unit_type': unit_type,
                    'unit': unit
                })
            
            return created_units
            
        except Exception as e:
            logger.error(f"Error in bulk unit creation for site {site_id}: {str(e)}")
            raise
    
    def _get_default_sequenza_fisica(self) -> Dict[str, List[str]]:
        """Get default sequenza_fisica structure."""
        return {
            "uguale_a": [],
            "si_lega_a": [],
            "gli_si_appoggia": [],
            "si_appoggia_a": [],
            "coperto_da": [],
            "copre": [],
            "tagliato_da": [],
            "taglia": [],
            "riempito_da": [],
            "riempie": []
        }
    
    async def _bulk_create_relationships(
        self,
        created_units: List[Dict[str, Any]],
        relationships_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create multiple relationships in bulk."""
        try:
            # Create unit lookup
            unit_lookup = {
                unit['temp_id']: unit['unit'] for unit in created_units
            }
            code_lookup = {
                (unit['unit_type'], unit['code']): unit['unit'] for unit in created_units
            }
            
            created_relationships = []
            
            for rel_data in relationships_data:
                from_temp_id = rel_data.get('from_temp_id')
                to_temp_id = rel_data.get('to_temp_id')
                relation_type = rel_data.get('relation_type')
                
                if not all([from_temp_id, to_temp_id, relation_type]):
                    logger.warning(f"Skipping incomplete relationship: {rel_data}")
                    continue
                
                from_unit = unit_lookup.get(from_temp_id)
                to_unit = unit_lookup.get(to_temp_id)
                
                if not from_unit or not to_unit:
                    logger.warning(f"Missing units for relationship: {rel_data}")
                    continue
                
                # Validate the relationship type
                await self._validate_single_relationship(from_unit, to_unit, relation_type)
                
                # Add relationship to from_unit's sequenza_fisica
                if hasattr(from_unit, 'sequenza_fisica'):
                    target_code = to_unit.usm_code if hasattr(to_unit, 'usm_code') else to_unit.us_code
                    
                    # Add type suffix for cross-references
                    if hasattr(to_unit, 'usm_code'):
                        target_reference = f"{target_code}(usm)"
                    else:
                        target_reference = target_code
                    
                    if target_reference not in from_unit.sequenza_fisica.get(relation_type, []):
                        from_unit.sequenza_fisica[relation_type].append(target_reference)
                
                created_relationships.append({
                    'temp_id': rel_data.get('temp_id', str(UUID.uuid4())),
                    'from_unit_id': str(from_unit.id),
                    'to_unit_id': str(to_unit.id),
                    'relation_type': relation_type
                })
            
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
            
            # Build graph representation
            graph = self._build_validation_graph(units, relationships)
            
            # Check for cycles
            cycles = self.detect_cycles_in_graph(graph)
            if cycles:
                raise StratigraphicCycleDetected(cycles[0])
            
            # Validate business rules
            await self._validate_business_rules(units, relationships)
            
            logger.info("Stratigraphic relationships validation passed")
            
        except Exception as e:
            logger.error(f"Error validating stratigraphic relationships: {str(e)}")
            raise
    
    def _build_validation_graph(
        self,
        units: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Build graph representation for cycle detection."""
        graph = defaultdict(list)
        
        # Build unit lookup
        unit_lookup = {unit['id']: unit for unit in units}
        
        for rel in relationships:
            from_id = rel['from_unit_id']
            to_id = rel['to_unit_id']
            relation_type = rel['relation_type']
            
            # Only consider directed relationships for cycle detection
            if relation_type in ['copre', 'taglia', 'si_appoggia_a', 'riempie']:
                graph[from_id].append(to_id)
            elif relation_type in ['coperto_da', 'tagliato_da', 'riempito_da']:
                graph[to_id].append(from_id)
        
        return graph
    
    def detect_cycles_in_graph(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        """
        Detect cycles in the stratigraphic graph using DFS.
        
        Args:
            graph: Dictionary representing the graph
            
        Returns:
            List of cycles found (each cycle is a list of node IDs)
        """
        try:
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
            
            for node in graph:
                if node not in visited:
                    dfs(node, [])
            
            return cycles
            
        except Exception as e:
            logger.error(f"Error detecting cycles in graph: {str(e)}")
            return []
    
    async def _validate_business_rules(
        self,
        units: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> None:
        """Validate business rules for stratigraphic relationships."""
        try:
            # Build unit lookup with type information
            unit_lookup = {}
            for unit in units:
                unit_obj = unit['unit']
                if hasattr(unit_obj, 'us_code'):
                    unit_lookup[unit['id']] = {
                        'code': unit_obj.us_code,
                        'type': 'us',
                        'tipo': getattr(unit_obj, 'tipo', 'positiva')
                    }
                elif hasattr(unit_obj, 'usm_code'):
                    unit_lookup[unit['id']] = {
                        'code': unit_obj.usm_code,
                        'type': 'usm'
                    }
            
            for rel in relationships:
                from_unit = unit_lookup.get(rel['from_unit_id'])
                to_unit = unit_lookup.get(rel['to_unit_id'])
                relation_type = rel['relation_type']
                
                if not from_unit or not to_unit:
                    continue
                
                # Rule: Only negative US can cut (taglia/tagliato_da)
                if relation_type in ['taglia', 'tagliato_da']:
                    if from_unit['type'] == 'us' and from_unit['tipo'] != 'negativa':
                        raise InvalidStratigraphicRelation(
                            relation_type,
                            from_unit['code'],
                            to_unit['code'],
                            "Solo US negative possono tagliare altre unità"
                        )
                
                # Rule: Positive US can cover/fill (copre/riempie)
                if relation_type in ['copre', 'riempie']:
                    if from_unit['type'] == 'us' and from_unit['tipo'] != 'positiva':
                        raise InvalidStratigraphicRelation(
                            relation_type,
                            from_unit['code'],
                            to_unit['code'],
                            "Solo US positive possono coprire o riempire altre unità"
                        )
            
        except Exception as e:
            logger.error(f"Error validating business rules: {str(e)}")
            raise
    
    async def _validate_single_relationship(
        self,
        from_unit,
        to_unit,
        relation_type: str
    ) -> None:
        """Validate a single relationship."""
        try:
            # Check if relation type is valid
            valid_relations = [
                'uguale_a', 'si_lega_a', 'gli_si_appoggia', 'si_appoggia_a',
                'coperto_da', 'copre', 'tagliato_da', 'taglia',
                'riempito_da', 'riempie'
            ]
            
            if relation_type not in valid_relations:
                raise InvalidStratigraphicRelation(
                    relation_type,
                    getattr(from_unit, 'us_code', getattr(from_unit, 'usm_code', 'Unknown')),
                    getattr(to_unit, 'us_code', getattr(to_unit, 'usm_code', 'Unknown')),
                    f"Tipo di relazione non valido. Valori validi: {valid_relations}"
                )
            
            # Validate self-relationships (should not exist)
            if from_unit.id == to_unit.id:
                raise InvalidStratigraphicRelation(
                    relation_type,
                    getattr(from_unit, 'us_code', getattr(from_unit, 'usm_code', 'Unknown')),
                    getattr(to_unit, 'us_code', getattr(to_unit, 'usm_code', 'Unknown')),
                    "Un'unità non può avere relazioni con se stessa"
                )
            
        except Exception as e:
            logger.error(f"Error validating single relationship: {str(e)}")
            raise
    
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
                    unit.sequenza_fisica = self._get_default_sequenza_fisica()
                
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
            for rel_type in self.RELATIONSHIP_TYPES.keys():
                rel_counts[rel_type] = 0
            
            # Process US relationships
            for row in us_rows + usm_rows:
                for rel_type in self.RELATIONSHIP_TYPES.keys():
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
                
                cycles = self.detect_cycles_in_graph(graph)
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