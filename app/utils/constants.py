# app/utils/constants.py
"""
Centralized constants for Harris Matrix and stratigraphy operations.

This module provides the single source of truth for relationship mappings
and other constants used across both frontend and backend.
"""

from typing import Dict

# ============================================================================
# RELATIONSHIP INVERSES - Single Source of Truth
# ============================================================================
# CRITICAL: These keys MUST match the sequenza_fisica JSON field keys.
# Frontend (harris_matrix_editor.html) uses a JavaScript copy that MUST match.
# All keys use snake_case format.

RELATIONSHIP_INVERSES: Dict[str, str] = {
    # Standard bidirectional relationships
    'copre': 'coperto_da',
    'coperto_da': 'copre',
    
    'taglia': 'tagliato_da',
    'tagliato_da': 'taglia',
    
    'riempie': 'riempito_da',
    'riempito_da': 'riempie',
    
    'si_appoggia_a': 'gli_si_appoggia',
    'gli_si_appoggia': 'si_appoggia_a',
    
    # Self-inverse relationships (symmetrical)
    'si_lega_a': 'si_lega_a',
    'uguale_a': 'uguale_a'
}

# Valid relationship types for validation
VALID_STRATIGRAPHIC_RELATIONS = list(RELATIONSHIP_INVERSES.keys())

# Directed relationships (have a from->to direction)
DIRECTED_RELATIONSHIPS = {'copre', 'taglia', 'si_appoggia_a', 'riempie'}

# Reverse directed relationships (the inverse of directed)
REVERSE_DIRECTED_RELATIONSHIPS = {'coperto_da', 'tagliato_da', 'gli_si_appoggia', 'riempito_da'}

# Bidirectional/Self-inverse relationships
BIDIRECTIONAL_RELATIONSHIPS = {'uguale_a', 'si_lega_a'}


def get_inverse_relationship(relationship_type: str) -> str:
    """
    Get the inverse relationship type for a given relationship.
    
    Args:
        relationship_type: The relationship type to find the inverse for
        
    Returns:
        The inverse relationship type, or the original if not found
    """
    return RELATIONSHIP_INVERSES.get(relationship_type, relationship_type)


def is_self_inverse(relationship_type: str) -> bool:
    """
    Check if a relationship type is self-inverse (symmetrical).
    
    Args:
        relationship_type: The relationship type to check
        
    Returns:
        True if the relationship is its own inverse
    """
    inverse = RELATIONSHIP_INVERSES.get(relationship_type)
    return inverse == relationship_type
