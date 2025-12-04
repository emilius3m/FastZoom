# app/utils/stratigraphy_helpers.py
"""
Centralized Utilities for Stratigraphy and Harris Matrix Operations

This module consolidates duplicated logic from harris_matrix_service.py,
harris_matrix.py (routes), and harris_matrix_validation.py into a
unified, reusable set of utilities.

Key Components:
- UnitLookupService: Centralized service for querying US/USM units
- StratigraphicGraphBuilder: Graph building for cycle detection and validation
- CycleDetector: Centralized cycle detection using DFS
- StratigraphicRulesValidator: Business rules validation logic
- Convenience functions for quick access to common operations
"""

import asyncio
import re
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from uuid import UUID, uuid4
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


# ============================================================================
# RELATIONSHIP TYPE CONSTANTS
# ============================================================================

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

DIRECTED_RELATIONSHIPS = {'copre', 'taglia', 'si_appoggia_a', 'riempie'}
REVERSE_DIRECTED_RELATIONSHIPS = {'coperto_da', 'tagliato_da', 'riempito_da'}
BIDIRECTIONAL_RELATIONSHIPS = {'uguale_a', 'si_lega_a', 'gli_si_appoggia'}
VALID_RELATIONSHIP_TYPES = list(RELATIONSHIP_TYPES.keys())


# ============================================================================
# UNIT LOOKUP SERVICE
# ============================================================================

class UnitLookupService:
    """
    Centralized service for querying US/USM units with caching and optimization.
    
    This service provides efficient lookup of stratigraphic units by code,
    site, and type, with built-in caching for performance optimization.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the unit lookup service.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        
    async def get_units_by_site(self, site_id: UUID) -> Tuple[List[UnitaStratigrafica], List[UnitaStratigraficaMuraria]]:
        """
        Get all US and USM units for a site with eager loading.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Tuple of (US units list, USM units list)
        """
        try:
            # Check cache first
            cache_key = f"site_units_{site_id}"
            if cache_key in self._cache:
                cached_data = self._cache[cache_key]
                if cached_data['timestamp'] > asyncio.get_event_loop().time() - self._cache_ttl:
                    return cached_data['data']
            
            # Query US units
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == str(site_id),
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            ).order_by(UnitaStratigrafica.us_code)
            
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            
            # Query USM units
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == str(site_id),
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            ).order_by(UnitaStratigraficaMuraria.usm_code)
            
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            # Cache the results
            result = (us_units, usm_units)
            self._cache[cache_key] = {
                'data': result,
                'timestamp': asyncio.get_event_loop().time()
            }
            
            logger.info(f"Found {len(us_units)} US units and {len(usm_units)} USM units for site {site_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error querying stratigraphic units for site_id {site_id}: {str(e)}")
            raise
    
    async def get_unit_by_code(self, site_id: UUID, unit_code: str, unit_type: str) -> Optional[Union[UnitaStratigrafica, UnitaStratigraficaMuraria]]:
        """
        Get a specific unit by code and type.
        
        Args:
            site_id: UUID of the archaeological site
            unit_code: Code of the unit (without prefix)
            unit_type: Type of unit ('us' or 'usm')
            
        Returns:
            Unit object or None if not found
        """
        try:
            if unit_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.us_code == unit_code,
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                return result.scalar_one_or_none()
            
            elif unit_type == 'usm':
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.site_id == str(site_id),
                        UnitaStratigraficaMuraria.usm_code == unit_code,
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                return result.scalar_one_or_none()
            
            else:
                raise ValueError(f"Invalid unit type: {unit_type}")
                
        except Exception as e:
            logger.error(f"Error getting unit {unit_type}{unit_code} for site {site_id}: {str(e)}")
            raise
    
    async def get_unit_by_id(self, site_id: UUID, unit_id: UUID, unit_type: str) -> Optional[Union[UnitaStratigrafica, UnitaStratigraficaMuraria]]:
        """
        Get a specific unit by ID and type.
        
        Args:
            site_id: UUID of the archaeological site
            unit_id: UUID of the unit
            unit_type: Type of unit ('us' or 'usm')
            
        Returns:
            Unit object or None if not found
        """
        try:
            if unit_type == 'us':
                query = select(UnitaStratigrafica).where(
                    and_(
                        UnitaStratigrafica.site_id == str(site_id),
                        UnitaStratigrafica.id == str(unit_id),
                        UnitaStratigrafica.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                return result.scalar_one_or_none()
            
            elif unit_type == 'usm':
                query = select(UnitaStratigraficaMuraria).where(
                    and_(
                        UnitaStratigraficaMuraria.site_id == str(site_id),
                        UnitaStratigraficaMuraria.id == str(unit_id),
                        UnitaStratigraficaMuraria.deleted_at.is_(None)
                    )
                )
                result = await self.db.execute(query)
                return result.scalar_one_or_none()
            
            else:
                raise ValueError(f"Invalid unit type: {unit_type}")
                
        except Exception as e:
            logger.error(f"Error getting unit {unit_type} with ID {unit_id} for site {site_id}: {str(e)}")
            raise
    
    def get_unit_lookup_dictionaries(self, us_units: List[UnitaStratigrafica], usm_units: List[UnitaStratigraficaMuraria]) -> Tuple[Dict[str, UnitaStratigrafica], Dict[str, UnitaStratigraficaMuraria]]:
        """
        Create lookup dictionaries for unit codes.
        
        Args:
            us_units: List of US units
            usm_units: List of USM units
            
        Returns:
            Tuple of (US lookup dict, USM lookup dict)
        """
        us_lookup = {us.us_code: us for us in us_units}
        usm_lookup = {usm.usm_code: usm for usm in usm_units}
        return us_lookup, usm_lookup
    
    async def check_code_conflicts(self, site_id: UUID, units_data: List[Dict[str, Any]]) -> None:
        """
        Check for existing unit codes in the site.
        
        Args:
            site_id: UUID of the archaeological site
            units_data: List of unit data dictionaries with 'code' and 'unit_type'
            
        Raises:
            UnitCodeConflict: If code conflicts are found
        """
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
    
    def invalidate_cache(self, site_id: Optional[UUID] = None) -> None:
        """
        Invalidate cached data.
        
        Args:
            site_id: Specific site ID to invalidate, or None to clear all cache
        """
        if site_id:
            cache_key = f"site_units_{site_id}"
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()
        
        logger.debug(f"Invalidated cache for site {site_id if site_id else 'all'}")


# ============================================================================
# STRATIGRAPHIC GRAPH BUILDER
# ============================================================================

class StratigraphicGraphBuilder:
    """
    Graph building utilities for cycle detection and validation.
    
    This class provides methods to build directed graphs from stratigraphic
    relationships, suitable for cycle detection and topological analysis.
    """
    
    def __init__(self, unit_lookup_service: UnitLookupService):
        """
        Initialize the graph builder.
        
        Args:
            unit_lookup_service: UnitLookupService instance for unit queries
        """
        self.unit_lookup = unit_lookup_service
    
    def build_graph_from_units(self, us_units: List[UnitaStratigrafica], usm_units: List[UnitaStratigraficaMuraria]) -> Dict[str, List[str]]:
        """
        Build directed graph from unit relationships.
        
        Args:
            us_units: List of US units
            usm_units: List of USM units
            
        Returns:
            Dictionary representing the directed graph
        """
        try:
            graph = defaultdict(list)
            
            # Create lookup dictionaries
            us_lookup, usm_lookup = self.unit_lookup.get_unit_lookup_dictionaries(us_units, usm_units)
            
            # Process US units
            for us in us_units:
                if us.sequenza_fisica:
                    self._process_unit_relationships(us.sequenza_fisica, f"US{us.us_code}", us_lookup, usm_lookup, graph)
            
            # Process USM units
            for usm in usm_units:
                if usm.sequenza_fisica:
                    self._process_unit_relationships(usm.sequenza_fisica, f"USM{usm.usm_code}", us_lookup, usm_lookup, graph)
            
            logger.info(f"Built directed graph with {len(graph)} nodes")
            return graph
            
        except Exception as e:
            logger.error(f"Error building graph from units: {str(e)}")
            raise
    
    def _process_unit_relationships(
        self,
        sequenza_fisica: Dict[str, List[str]],
        source_node: str,
        us_lookup: Dict[str, UnitaStratigrafica],
        usm_lookup: Dict[str, UnitaStratigraficaMuraria],
        graph: Dict[str, List[str]]
    ) -> None:
        """
        Process relationships for a single unit and add to graph.
        
        Args:
            sequenza_fisica: JSON structure containing relationships
            source_node: Source node identifier
            us_lookup: Dictionary mapping US codes to US objects
            usm_lookup: Dictionary mapping USM codes to USM objects
            graph: Graph dictionary to modify
        """
        for rel_type, targets in sequenza_fisica.items():
            if not targets or rel_type not in RELATIONSHIP_TYPES:
                continue
            
            for target in targets:
                # Parse target to handle cross-references like "174(usm)"
                target_code, target_type = self._parse_target_reference(target)
                
                # Check if target exists
                target_exists = False
                if target_type == 'us' and target_code in us_lookup:
                    target_exists = True
                elif target_type == 'usm' and target_code in usm_lookup:
                    target_exists = True
                
                if not target_exists:
                    continue
                
                # Create target node identifier
                target_node = f"{target_type.upper()}{target_code}"
                
                # Add directed edge based on relationship type
                if rel_type in DIRECTED_RELATIONSHIPS:
                    # These are "from source to target" relationships
                    graph[source_node].append(target_node)
                elif rel_type in REVERSE_DIRECTED_RELATIONSHIPS:
                    # These are "from target to source" relationships
                    graph[target_node].append(source_node)
                # Bidirectional relationships don't affect chronological ordering
    
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
    
    def build_validation_graph(
        self,
        units: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """
        Build graph representation for cycle detection from validation data.
        
        Args:
            units: List of unit dictionaries
            relationships: List of relationship dictionaries
            
        Returns:
            Dictionary representing the directed graph
        """
        try:
            graph = defaultdict(list)
            
            # Build unit lookup
            unit_lookup = {unit['id']: unit for unit in units}
            
            for rel in relationships:
                from_id = rel['from_unit_id']
                to_id = rel['to_unit_id']
                relation_type = rel['relation_type']
                
                # Only consider directed relationships for cycle detection
                if relation_type in DIRECTED_RELATIONSHIPS:
                    graph[from_id].append(to_id)
                elif relation_type in REVERSE_DIRECTED_RELATIONSHIPS:
                    graph[to_id].append(from_id)
            
            return graph
            
        except Exception as e:
            logger.error(f"Error building validation graph: {str(e)}")
            raise
    
    def calculate_chronological_levels(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, int]:
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
        try:
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
                    if edge['type'] in DIRECTED_RELATIONSHIPS:
                        # from_node is more recent than to_node
                        graph[from_node].append(to_node)
                        in_degree[to_node] += 1
                    elif edge['type'] in REVERSE_DIRECTED_RELATIONSHIPS:
                        # from_node is older than to_node
                        graph[to_node].append(from_node)
                        in_degree[from_node] += 1
                    # Bidirectional relationships don't affect chronological ordering
            
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
            
        except Exception as e:
            logger.error(f"Error calculating chronological levels: {str(e)}")
            raise


# ============================================================================
# CYCLE DETECTOR
# ============================================================================

class CycleDetector:
    """
    Centralized cycle detection using DFS algorithm.
    
    This class provides efficient cycle detection in directed graphs,
    specifically designed for stratigraphic relationship validation.
    """
    
    @staticmethod
    def detect_cycles_in_graph(graph: Dict[str, List[str]]) -> List[List[str]]:
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
    
    @staticmethod
    def detect_cycles_from_relationships(relationships: List[Dict[str, Any]]) -> List[List[str]]:
        """
        Detect cycles directly from relationship data.
        
        Args:
            relationships: List of relationship dictionaries
            
        Returns:
            List of cycles found
        """
        try:
            # Build graph from relationships
            graph = defaultdict(list)
            
            for rel in relationships:
                from_id = rel['from_unit_id']
                to_id = rel['to_unit_id']
                relation_type = rel['relation_type']
                
                # Only consider directed relationships
                if relation_type in DIRECTED_RELATIONSHIPS:
                    graph[from_id].append(to_id)
                elif relation_type in REVERSE_DIRECTED_RELATIONSHIPS:
                    graph[to_id].append(from_id)
            
            return CycleDetector.detect_cycles_in_graph(graph)
            
        except Exception as e:
            logger.error(f"Error detecting cycles from relationships: {str(e)}")
            return []
    
    @staticmethod
    def has_cycles(graph: Dict[str, List[str]]) -> bool:
        """
        Quick check if graph has any cycles.
        
        Args:
            graph: Dictionary representing the graph
            
        Returns:
            True if cycles exist, False otherwise
        """
        cycles = CycleDetector.detect_cycles_in_graph(graph)
        return len(cycles) > 0
    
    @staticmethod
    def get_affected_nodes(cycles: List[List[str]]) -> Set[str]:
        """
        Get all nodes involved in cycles.
        
        Args:
            cycles: List of cycles
            
        Returns:
            Set of affected node IDs
        """
        affected_nodes = set()
        for cycle in cycles:
            affected_nodes.update(cycle)
        return affected_nodes


# ============================================================================
# STRATIGRAPHIC RULES VALIDATOR
# ============================================================================

class StratigraphicRulesValidator:
    """
    Business rules validation logic for stratigraphic relationships.
    
    This class encapsulates all business rule validation logic for
    ensuring that stratigraphic relationships follow archaeological
    principles and domain constraints.
    """
    
    @staticmethod
    def validate_business_rules(
        units: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> None:
        """
        Validate business rules for stratigraphic relationships.
        
        Args:
            units: List of unit dictionaries
            relationships: List of relationship dictionaries
            
        Raises:
            InvalidStratigraphicRelation: If business rules are violated
        """
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
    
    @staticmethod
    def validate_single_relationship(
        from_unit,
        to_unit,
        relation_type: str
    ) -> None:
        """
        Validate a single relationship.
        
        Args:
            from_unit: Source unit object
            to_unit: Target unit object
            relation_type: Type of relationship
            
        Raises:
            InvalidStratigraphicRelation: If validation fails
        """
        try:
            # Check if relation type is valid
            if relation_type not in VALID_RELATIONSHIP_TYPES:
                raise InvalidStratigraphicRelation(
                    relation_type,
                    getattr(from_unit, 'us_code', getattr(from_unit, 'usm_code', 'Unknown')),
                    getattr(to_unit, 'us_code', getattr(to_unit, 'usm_code', 'Unknown')),
                    f"Tipo di relazione non valido. Valori validi: {VALID_RELATIONSHIP_TYPES}"
                )
            
            # Validate self-relationships (should not exist)
            if from_unit.id == to_unit.id:
                raise InvalidStratigraphicRelation(
                    relation_type,
                    getattr(from_unit, 'us_code', getattr(from_unit, 'usm_code', 'Unknown')),
                    getattr(to_unit, 'us_code', getattr(to_unit, 'usm_code', 'Unknown')),
                    "Un'unità non può avere relazioni con se stessa"
                )
            
            # Additional US type validation
            if hasattr(from_unit, 'tipo'):
                from_code = getattr(from_unit, 'us_code', 'Unknown')
                to_code = getattr(to_unit, 'us_code', getattr(to_unit, 'usm_code', 'Unknown'))
                
                # Rule: Only negative US can cut
                if relation_type in ['taglia', 'tagliato_da']:
                    if from_unit.tipo != 'negativa':
                        raise InvalidStratigraphicRelation(
                            relation_type,
                            from_code,
                            to_code,
                            "Solo US negative possono tagliare altre unità"
                        )
                
                # Rule: Positive US can cover/fill
                if relation_type in ['copre', 'riempie']:
                    if from_unit.tipo != 'positiva':
                        raise InvalidStratigraphicRelation(
                            relation_type,
                            from_code,
                            to_code,
                            "Solo US positive possono coprire o riempire altre unità"
                        )
            
        except Exception as e:
            logger.error(f"Error validating single relationship: {str(e)}")
            raise
    
    @staticmethod
    def validate_relationship_type(relation_type: str) -> None:
        """
        Validate if a relationship type is valid.
        
        Args:
            relation_type: Type of relationship to validate
            
        Raises:
            InvalidStratigraphicRelation: If type is invalid
        """
        if relation_type not in VALID_RELATIONSHIP_TYPES:
            raise InvalidStratigraphicRelation(
                relation_type,
                'unknown',
                'unknown',
                f"Tipo di relazione non valido. Valori validi: {VALID_RELATIONSHIP_TYPES}"
            )
    
    @staticmethod
    def is_bidirectional_relationship(relation_type: str) -> bool:
        """
        Check if a relationship type is bidirectional.
        
        Args:
            relation_type: Type of relationship
            
        Returns:
            True if bidirectional, False otherwise
        """
        return relation_type in BIDIRECTIONAL_RELATIONSHIPS
    
    @staticmethod
    def is_directed_relationship(relation_type: str) -> bool:
        """
        Check if a relationship type is directed.
        
        Args:
            relation_type: Type of relationship
            
        Returns:
            True if directed, False otherwise
        """
        return relation_type in DIRECTED_RELATIONSHIPS or relation_type in REVERSE_DIRECTED_RELATIONSHIPS


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_default_sequenza_fisica() -> Dict[str, List[str]]:
    """
    Get default sequenza_fisica structure.
    
    Returns:
        Dictionary with empty relationship lists
    """
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


def parse_target_reference(target: str) -> Tuple[str, str]:
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


def build_nodes_for_graph(
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
        node = {
            'id': f"US{us.us_code}",
            'type': 'us',
            'label': us.us_code,
            'definition': us.definizione or '',
            'tipo': getattr(us, 'tipo', 'positiva') or 'positiva',
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
    
    return nodes


def build_edges_from_relationships(relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build edge list for graph visualization from relationships.
    
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
    
    return edges


def validate_relationship_direction(
    from_node: str,
    to_node: str,
    relation_type: str
) -> Tuple[str, str]:
    """
    Determine the correct direction for a relationship edge.
    
    Args:
        from_node: Source node identifier
        to_node: Target node identifier
        relation_type: Type of relationship
        
    Returns:
        Tuple of (edge_from, edge_to) with correct direction
    """
    rel_config = RELATIONSHIP_TYPES.get(relation_type, {})
    
    if rel_config.get('bidirectional', False):
        # For bidirectional relationships, create edge from source to target
        return from_node, to_node
    elif relation_type in REVERSE_DIRECTED_RELATIONSHIPS:
        # These are "from target to source" relationships
        return to_node, from_node
    else:
        # These are "from source to target" relationships
        return from_node, to_node


async def generate_sequential_codes(site_id: UUID, db: AsyncSession, units_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate sequential codes for units without explicit codes.
    
    Args:
        site_id: UUID of the archaeological site
        db: AsyncSession for database operations
        units_data: List of unit data dictionaries
        
    Returns:
        Updated list with generated codes
    """
    try:
        # Get current max codes
        us_max_query = select(func.max(UnitaStratigrafica.us_code)).where(
            and_(
                UnitaStratigrafica.site_id == str(site_id),
                UnitaStratigrafica.deleted_at.is_(None)
            )
        )
        us_max_result = await db.execute(us_max_query)
        us_max = us_max_result.scalar() or 0
        
        usm_max_query = select(func.max(UnitaStratigraficaMuraria.usm_code)).where(
            and_(
                UnitaStratigraficaMuraria.site_id == str(site_id),
                UnitaStratigraficaMuraria.deleted_at.is_(None)
            )
        )
        usm_max_result = await db.execute(usm_max_query)
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


# ============================================================================
# COMPREHENSIVE VALIDATION FUNCTION
# ============================================================================

async def validate_stratigraphic_data(
    db: AsyncSession,
    site_id: UUID,
    units_data: List[Dict[str, Any]] = None,
    relationships_data: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Comprehensive validation of stratigraphic data with all helper classes.
    
    This function provides a one-stop validation solution that uses all the
    helper classes to perform complete validation of stratigraphic data.
    
    Args:
        db: AsyncSession for database operations
        site_id: UUID of the archaeological site
        units_data: Optional list of unit data for validation
        relationships_data: Optional list of relationship data for validation
        
    Returns:
        Dictionary with validation results
    """
    try:
        logger.info(f"Starting comprehensive stratigraphic validation for site {site_id}")
        
        # Initialize services
        unit_lookup = UnitLookupService(db)
        graph_builder = StratigraphicGraphBuilder(unit_lookup)
        rules_validator = StratigraphicRulesValidator()
        
        # Get existing units if no new data provided
        if not units_data:
            us_units, usm_units = await unit_lookup.get_units_by_site(site_id)
            units_data = []
            relationships_data = []
            
            # Convert existing units to validation format
            for us in us_units:
                units_data.append({
                    'id': str(us.id),
                    'unit_type': 'us',
                    'unit': us
                })
                
                if us.sequenza_fisica:
                    for rel_type, targets in us.sequenza_fisica.items():
                        if targets:
                            for target in targets:
                                target_code, target_type = parse_target_reference(target)
                                target_unit = await unit_lookup.get_unit_by_code(site_id, target_code, target_type)
                                if target_unit:
                                    relationships_data.append({
                                        'from_unit_id': str(us.id),
                                        'to_unit_id': str(target_unit.id),
                                        'relation_type': rel_type
                                    })
            
            for usm in usm_units:
                units_data.append({
                    'id': str(usm.id),
                    'unit_type': 'usm',
                    'unit': usm
                })
                
                if usm.sequenza_fisica:
                    for rel_type, targets in usm.sequenza_fisica.items():
                        if targets:
                            for target in targets:
                                target_code, target_type = parse_target_reference(target)
                                target_unit = await unit_lookup.get_unit_by_code(site_id, target_code, target_type)
                                if target_unit:
                                    relationships_data.append({
                                        'from_unit_id': str(usm.id),
                                        'to_unit_id': str(target_unit.id),
                                        'relation_type': rel_type
                                    })
        
        validation_result = {
            'site_id': str(site_id),
            'validation_timestamp': None,
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'business_rules': {
                'cycles_detected': False,
                'negative_cutting_violations': 0,
                'positive_covering_violations': 0,
                'self_references': 0,
                'invalid_relationship_types': 0
            },
            'statistics': {
                'total_units': len(units_data),
                'total_relationships': len(relationships_data),
                'us_units': len([u for u in units_data if u.get('unit_type') == 'us']),
                'usm_units': len([u for u in units_data if u.get('unit_type') == 'usm'])
            }
        }
        
        # 1. Validate business rules
        try:
            await rules_validator.validate_business_rules(units_data, relationships_data)
            logger.info("Business rules validation passed")
        except InvalidStratigraphicRelation as e:
            validation_result['is_valid'] = False
            validation_result['errors'].append(str(e))
            validation_result['business_rules']['invalid_relationship_types'] += 1
        
        # 2. Detect cycles
        try:
            graph = graph_builder.build_validation_graph(units_data, relationships_data)
            cycles = CycleDetector.detect_cycles_in_graph(graph)
            
            if cycles:
                validation_result['is_valid'] = False
                validation_result['business_rules']['cycles_detected'] = True
                validation_result['errors'].append(f"Stratigraphic cycles detected: {cycles}")
                
                # Get affected nodes
                affected_nodes = CycleDetector.get_affected_nodes(cycles)
                validation_result['warnings'].append(f"Cycles affect {len(affected_nodes)} units")
            else:
                logger.info("No cycles detected")
                
        except Exception as e:
            logger.error(f"Error in cycle detection: {str(e)}")
            validation_result['errors'].append(f"Cycle detection error: {str(e)}")
        
        # 3. Check for orphaned units
        if relationships_data and units_data:
            referenced_unit_ids = set()
            for rel in relationships_data:
                referenced_unit_ids.add(rel['from_unit_id'])
                referenced_unit_ids.add(rel['to_unit_id'])
            
            orphaned_units = [unit for unit in units_data if unit['id'] not in referenced_unit_ids]
            if orphaned_units:
                validation_result['warnings'].append(f"Found {len(orphaned_units)} units without relationships")
        
        # 4. Performance warnings
        if len(units_data) > 100:
            validation_result['warnings'].append("Large number of units may impact performance")
        
        if len(relationships_data) > len(units_data) * 3:
            validation_result['warnings'].append("High density of relationships detected")
        
        logger.info(f"Stratigraphic validation completed: {'PASS' if validation_result['is_valid'] else 'FAIL'}")
        return validation_result
        
    except Exception as e:
        logger.error(f"Error in comprehensive stratigraphic validation: {str(e)}")
        return {
            'site_id': str(site_id),
            'is_valid': False,
            'errors': [f"Validation system error: {str(e)}"],
            'warnings': [],
            'business_rules': {},
            'statistics': {}
        }


# ============================================================================
# FACTORY FUNCTIONS FOR EASY INITIALIZATION
# ============================================================================

def create_unit_lookup_service(db: AsyncSession) -> UnitLookupService:
    """
    Factory function to create UnitLookupService.
    
    Args:
        db: AsyncSession for database operations
        
    Returns:
        UnitLookupService instance
    """
    return UnitLookupService(db)


def create_graph_builder(unit_lookup: UnitLookupService) -> StratigraphicGraphBuilder:
    """
    Factory function to create StratigraphicGraphBuilder.
    
    Args:
        unit_lookup: UnitLookupService instance
        
    Returns:
        StratigraphicGraphBuilder instance
    """
    return StratigraphicGraphBuilder(unit_lookup)


def create_rules_validator() -> StratigraphicRulesValidator:
    """
    Factory function to create StratigraphicRulesValidator.
    
    Returns:
        StratigraphicRulesValidator instance
    """
    return StratigraphicRulesValidator()


def create_complete_validation_suite(db: AsyncSession, site_id: UUID) -> Dict[str, Any]:
    """
    Factory function to create complete validation suite.
    
    Args:
        db: AsyncSession for database operations
        site_id: UUID of the archaeological site
        
    Returns:
        Dictionary with all helper services
    """
    unit_lookup = UnitLookupService(db)
    graph_builder = StratigraphicGraphBuilder(unit_lookup)
    rules_validator = StratigraphicRulesValidator()
    cycle_detector = CycleDetector()
    
    return {
        'unit_lookup': unit_lookup,
        'graph_builder': graph_builder,
        'rules_validator': rules_validator,
        'cycle_detector': cycle_detector,
        'site_id': site_id
    }