# app/routes/shared/__init__.py - Shared router utilities package
"""
Shared utilities for router consolidation.
Provides common patterns and services used across multiple routers.
"""

from .router_utils import (
    get_base_context,
    get_current_user_with_context,
    create_user_context,
    handle_permission_denied,
    handle_resource_not_found,
    get_site_access,
    RouterUtils
)

__all__ = [
    'get_base_context',
    'get_current_user_with_context',
    'create_user_context',
    'handle_permission_denied',
    'handle_resource_not_found',
    'get_site_access',
    'RouterUtils'
]