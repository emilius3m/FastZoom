# app/services/harris_matrix_service.py
"""
Service for generating Harris Matrix graph data from US/USM stratigraphic relationships.

This service queries both US and USM tables for a given site_id, extracts relationships
from the sequenza_fisica JSON field, and generates graph data structures suitable
for Cytoscape.js visualization with topological sorting for chronological levels.
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID
from collections import defaultdict, deque

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from loguru import logger

from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria


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