"""
FastZoom exceptions package.

This package provides specialized exceptions for different modules
including Harris Matrix, authentication, and general application errors.
"""

from .harris_matrix import (
    HarrisMatrixException,
    UnitCodeConflict,
    InvalidStratigraphicRelation,
    CycleDetectionError,
    BulkOperationError,
    ValidationTimeoutError,
    StaleReferenceError
)

# Import BusinessLogicError from the main exceptions module
from ..exceptions import BusinessLogicError

__all__ = [
    'HarrisMatrixException',
    'UnitCodeConflict',
    'InvalidStratigraphicRelation',
    'CycleDetectionError',
    'BulkOperationError',
    'ValidationTimeoutError',
    'StaleReferenceError',
    'BusinessLogicError'
]