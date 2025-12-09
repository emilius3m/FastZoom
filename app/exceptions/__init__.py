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

# Define BusinessLogicError directly to avoid circular import
class BusinessLogicError(Exception):
    """Exception for business logic errors."""
    
    def __init__(self, message: str, status_code: int = 400):
        """
        Initialize business logic error.
        
        Args:
            message: Error message
            status_code: HTTP status code (default: 400)
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

# Define aliases for commonly used exceptions to maintain compatibility
HarrisMatrixValidationError = InvalidStratigraphicRelation
StratigraphicCycleDetected = CycleDetectionError
HarrisMatrixServiceError = HarrisMatrixException

__all__ = [
    'HarrisMatrixException',
    'UnitCodeConflict',
    'InvalidStratigraphicRelation',
    'CycleDetectionError',
    'BulkOperationError',
    'ValidationTimeoutError',
    'StaleReferenceError',
    'BusinessLogicError',
    'HarrisMatrixValidationError',
    'StratigraphicCycleDetected',
    'HarrisMatrixServiceError'
]