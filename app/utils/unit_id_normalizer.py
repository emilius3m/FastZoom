# app/utils/unit_id_normalizer.py
"""
Utility functions for normalizing unit IDs by removing existing prefixes.

This module provides functions to handle US/USM ID normalization across the system,
ensuring consistent ID handling and preventing double prefixing issues.
"""

import re
from typing import Optional

def normalize_unit_id(unit_id: str) -> str:
    """
    Remove existing US/USM prefixes from a unit ID and return the clean code.
    
    This function handles various ID formats:
    - "US001" -> "001"
    - "USM001" -> "001" 
    - "USUS001" -> "001" (removes double prefixes)
    - "001" -> "001" (already clean)
    
    Args:
        unit_id: Unit ID that may contain prefixes
        
    Returns:
        Clean unit ID without prefixes
        
    Examples:
        >>> normalize_unit_id("US001")
        '001'
        >>> normalize_unit_id("USM001")
        '001'
        >>> normalize_unit_id("USUS001")
        '001'
        >>> normalize_unit_id("001")
        '001'
    """
    if not unit_id:
        return unit_id
    
    # Remove whitespace
    unit_id = unit_id.strip()
    
    # Pattern to match US/USM prefixes at the start (case-insensitive)
    # This will match: US, USM, us, usm, USUS, USMUS, usus, usmus, USUSUS, etc.
    prefix_pattern = r'^(USM?)+'
    
    # Remove all US/USM prefixes from the beginning (case-insensitive)
    clean_id = re.sub(prefix_pattern, '', unit_id, flags=re.IGNORECASE)
    
    return clean_id

def get_unit_prefix(unit_type: str) -> str:
    """
    Get the appropriate prefix for a unit type.
    
    Args:
        unit_type: Type of unit ('us' or 'usm')
        
    Returns:
        Prefix string ('US' or 'USM')
    """
    return "USM" if unit_type.lower() == 'usm' else "US"

def create_unit_display_name(unit_id: str, unit_type: str) -> str:
    """
    Create a properly formatted unit display name with prefix.
    
    This function ensures no double prefixing by normalizing the unit_id first
    and then adding the appropriate prefix.
    
    Args:
        unit_id: Unit ID that may contain prefixes
        unit_type: Type of unit ('us' or 'usm')
        
    Returns:
        Properly formatted display name with single prefix
        
    Examples:
        >>> create_unit_display_name("001", "us")
        'US001'
        >>> create_unit_display_name("US001", "us")
        'US001'
        >>> create_unit_display_name("USUS001", "us")
        'US001'
    """
    clean_id = normalize_unit_id(unit_id)
    prefix = get_unit_prefix(unit_type)
    return f"{prefix}{clean_id}"

def create_graph_node_id(unit_id: str, unit_type: str) -> str:
    """
    Create a graph node identifier for the given unit.
    
    This ensures consistent node ID creation across the system,
    preventing double prefixes in graph operations.
    
    Args:
        unit_id: Unit ID that may contain prefixes
        unit_type: Type of unit ('us' or 'usm')
        
    Returns:
        Graph node identifier with single prefix
    """
    return create_unit_display_name(unit_id, unit_type)

def is_valid_unit_code_pattern(unit_id: str) -> bool:
    """
    Validate if a unit ID matches the expected pattern.
    
    This updated pattern rejects double prefixes while accepting
    valid single-prefix formats.
    
    Args:
        unit_id: Unit ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not unit_id:
        return False
    
    # Updated pattern that rejects double prefixes
    # - ^US\d+$ matches US001, US123, etc.
    # - ^USM\d+$ matches USM001, USM123, etc.
    # - ^\d+$ matches plain numbers 001, 123, etc.
    # The pattern prevents USUS..., USMUS..., etc.
    pattern = r'^(?:US\d+|USM\d+|\d+)$'
    
    return bool(re.match(pattern, unit_id))

def validate_and_normalize_unit_id(unit_id: str, unit_type: str) -> str:
    """
    Validate and normalize a unit ID for storage/processing.
    
    This is a comprehensive function that both validates the format
    and normalizes the ID to ensure consistency.
    
    Args:
        unit_id: Unit ID to validate and normalize
        unit_type: Type of unit ('us' or 'usm')
        
    Returns:
        Normalized unit ID (numeric part only)
        
    Raises:
        ValueError: If the unit ID format is invalid
    """
    if not unit_id:
        raise ValueError("Unit ID cannot be empty")
    
    # Validate the pattern
    if not is_valid_unit_code_pattern(unit_id):
        raise ValueError(
            f"Invalid unit ID format: {unit_id}. "
            f"Expected format: US001, USM001, or 001. "
            f"Double prefixes like USUS001 are not allowed."
        )
    
    # Return the clean numeric part
    return normalize_unit_id(unit_id)

# ============================================================================
# CONVENIENCE FUNCTIONS FOR COMMON USE CASES
# ============================================================================

def fix_double_prefixed_id(double_prefixed_id: str) -> str:
    """
    Fix a double-prefixed ID by removing duplicate prefixes.
    
    Args:
        double_prefixed_id: ID with double prefixes like "USUS001"
        
    Returns:
        Single-prefixed ID like "US001"
        
    Examples:
        >>> fix_double_prefixed_id("USUS001")
        'US001'
        >>> fix_double_prefixed_id("USMUSM001")
        'USM001'
        >>> fix_double_prefixed_id("001")
        '001'  # Plain number, no prefix to fix
    """
    if not double_prefixed_id:
        return double_prefixed_id
    
    # Check if it starts with a prefix at all
    if double_prefixed_id.startswith("US"):
        # Determine unit type from the prefix
        if double_prefixed_id.startswith("USM"):
            unit_type = "usm"
        else:
            unit_type = "us"
        
        return create_unit_display_name(double_prefixed_id, unit_type)
    else:
        # Plain number, no prefix to fix - return as-is
        return double_prefixed_id

def normalize_unit_id_list(unit_ids: list) -> list:
    """
    Normalize a list of unit IDs.
    
    Args:
        unit_ids: List of unit IDs to normalize
        
    Returns:
        List of normalized unit IDs
    """
    return [normalize_unit_id(unit_id) for unit_id in unit_ids]