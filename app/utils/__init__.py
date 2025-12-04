# app/utils/__init__.py
"""
Utilities package for FastZoom.

This package contains centralized utility modules that provide
reusable functionality across different parts of the application.
"""

from .stratigraphy_helpers import (
    # Classes
    UnitLookupService,
    StratigraphicGraphBuilder,
    CycleDetector,
    StratigraphicRulesValidator,
    
    # Constants
    RELATIONSHIP_TYPES,
    DIRECTED_RELATIONSHIPS,
    REVERSE_DIRECTED_RELATIONSHIPS,
    BIDIRECTIONAL_RELATIONSHIPS,
    VALID_RELATIONSHIP_TYPES,
    
    # Convenience Functions
    get_default_sequenza_fisica,
    parse_target_reference,
    build_nodes_for_graph,
    build_edges_from_relationships,
    validate_relationship_direction,
    generate_sequential_codes,
    validate_stratigraphic_data,
    
    # Factory Functions
    create_unit_lookup_service,
    create_graph_builder,
    create_rules_validator,
    create_complete_validation_suite
)

__all__ = [
    # Classes
    'UnitLookupService',
    'StratigraphicGraphBuilder',
    'CycleDetector',
    'StratigraphicRulesValidator',
    
    # Constants
    'RELATIONSHIP_TYPES',
    'DIRECTED_RELATIONSHIPS',
    'REVERSE_DIRECTED_RELATIONSHIPS',
    'BIDIRECTIONAL_RELATIONSHIPS',
    'VALID_RELATIONSHIP_TYPES',
    
    # Convenience Functions
    'get_default_sequenza_fisica',
    'parse_target_reference',
    'build_nodes_for_graph',
    'build_edges_from_relationships',
    'validate_relationship_direction',
    'generate_sequential_codes',
    'validate_stratigraphic_data',
    
    # Factory Functions
    'create_unit_lookup_service',
    'create_graph_builder',
    'create_rules_validator',
    'create_complete_validation_suite'
]