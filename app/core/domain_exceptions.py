"""
Domain Exception Hierarchy for FastZoom Application

This module defines a comprehensive exception hierarchy that replaces HTTPException
usage in service layers, following clean architecture principles.
"""

from typing import Optional, Any, Dict


# ============================================================================
# Base Domain Exception
# ============================================================================

class DomainException(Exception):
    """
    Base exception for all domain-level errors.
    
    Domain exceptions represent business logic errors and should be caught
    by the presentation layer (routes) and converted to appropriate HTTP responses.
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize domain exception.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code for API responses
            details: Additional context about the error
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


# ============================================================================
# Authentication & Authorization Exceptions
# ============================================================================

class AuthenticationError(DomainException):
    """User authentication failed."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Invalid username or password."""
    pass


class UserInactiveError(AuthenticationError):
    """User account is inactive."""
    pass


class TokenExpiredError(AuthenticationError):
    """Authentication token has expired."""
    pass


class TokenInvalidError(AuthenticationError):
    """Authentication token is invalid."""
    pass


class AuthorizationError(DomainException):
    """User is not authorized to perform this action."""
    pass


class InsufficientPermissionsError(AuthorizationError):
    """User lacks required permissions."""
    pass


class NoSiteAccessError(AuthorizationError):
    """User has no access to any archaeological sites."""
    pass


# ============================================================================
# Resource Exceptions
# ============================================================================

class ResourceError(DomainException):
    """Base exception for resource-related errors."""
    pass


class ResourceNotFoundError(ResourceError):
    """Requested resource does not exist."""
    
    def __init__(
        self, 
        resource_type: str, 
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"{resource_type} not found"
        if resource_id:
            message += f": {resource_id}"
        super().__init__(message, details=details)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceAlreadyExistsError(ResourceError):
    """Resource with this identifier already exists."""
    
    def __init__(
        self, 
        resource_type: str, 
        identifier: str,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"{resource_type} already exists: {identifier}"
        super().__init__(message, details=details)
        self.resource_type = resource_type
        self.identifier = identifier


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationError(DomainException):
    """Input validation failed."""
    
    def __init__(
        self, 
        message: str, 
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details=details)
        self.field = field


class InvalidInputError(ValidationError):
    """Input data is invalid."""
    pass


class MissingRequiredFieldError(ValidationError):
    """Required field is missing."""
    pass


# ============================================================================
# Storage Exceptions (already defined in core/exceptions.py)
# These are re-exported here for completeness
# ============================================================================

class StorageError(DomainException):
    """Base exception for storage-related errors."""
    pass


class StorageFullError(StorageError):
    """Storage is full and cleanup couldn't free enough space."""
    
    def __init__(self, message: str, freed_space_mb: int = 0):
        super().__init__(message)
        self.freed_space_mb = freed_space_mb


class StorageTemporaryError(StorageError):
    """Temporary storage error - retry may succeed."""
    pass


class StorageConnectionError(StorageError):
    """Cannot connect to storage system."""
    pass


class StorageNotFoundError(StorageError):
    """File or object not found in storage."""
    pass


class StoragePermissionError(StorageError):
    """Permission denied for storage operation."""
    pass


class StorageValidationError(StorageError):
    """Storage data validation failed."""
    pass


# ============================================================================
# Photo Service Exceptions
# ============================================================================

class PhotoServiceError(DomainException):
    """Base exception for photo service errors."""
    pass


class ImageProcessingError(PhotoServiceError):
    """Error processing image file."""
    pass


class UnsupportedImageFormatError(PhotoServiceError):
    """Image format is not supported."""
    pass


class InvalidImageError(PhotoServiceError):
    """Image file is corrupted or invalid."""
    pass


class FileUploadError(PhotoServiceError):
    """Error uploading file."""
    pass


# ============================================================================
# Photo Service Exceptions
# ============================================================================

class PhotoNotFoundError(ResourceNotFoundError):
    """Photo not found."""
    
    def __init__(self, photo_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("Photo", photo_id, details)


# ============================================================================
# Site Management Exceptions
# ============================================================================

class SiteError(DomainException):
    """Base exception for site-related errors."""
    pass


class SiteNotFoundError(ResourceNotFoundError):
    """Archaeological site not found."""
    
    def __init__(self, site_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ArchaeologicalSite", site_id, details)


class SiteAccessDeniedError(AuthorizationError):
    """User cannot access this archaeological site."""
    
    def __init__(self, site_id: str, user_id: str, details: Optional[Dict[str, Any]] = None):
        message = f"Access denied to site {site_id} for user {user_id}"
        super().__init__(message, details=details)
        self.site_id = site_id
        self.user_id = user_id


# ============================================================================
# Harris Matrix Exceptions (from app/exceptions/harris_matrix.py)
# These should be moved here for centralization
# ============================================================================

class HarrisMatrixException(DomainException):
    """Base exception for Harris Matrix operations."""
    pass


class UnitCodeConflict(HarrisMatrixException):
    """Unit code already exists in this site."""
    
    def __init__(self, code: str, unit_type: Optional[str] = None):
        prefix = f"{unit_type.upper()}:" if unit_type else "Unità"
        message = f"{prefix} Il codice '{code}' esiste già in questo sito"
        super().__init__(message)
        self.code = code
        self.unit_type = unit_type


class InvalidStratigraphicRelation(HarrisMatrixException):
    """Stratigraphic relationship is invalid."""
    
    def __init__(
        self, 
        relation_type: str, 
        from_unit: Optional[str] = None, 
        to_unit: Optional[str] = None, 
        reason: Optional[str] = None
    ):
        message = f"Relazione stratigrafica non valida: {relation_type}"
        if from_unit and to_unit:
            message += f" da {from_unit} a {to_unit}"
        if reason:
            message += f" - {reason}"
        super().__init__(message)
        self.relation_type = relation_type
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.reason = reason


class CycleDetectionError(HarrisMatrixException):
    """Cycle detected in stratigraphic relationships."""
    
    def __init__(self, cycle_path: Optional[list] = None):
        message = "Ciclo stratigrafico rilevato nelle relazioni"
        if cycle_path:
            message += f": {' -> '.join(cycle_path)}"
        super().__init__(message)
        self.cycle_path = cycle_path


class BulkOperationError(HarrisMatrixException):
    """Bulk operation on Harris Matrix failed."""
    pass


class ValidationTimeoutError(HarrisMatrixException):
    """Harris Matrix validation timed out."""
    pass


class StaleReferenceError(HarrisMatrixException):
    """Reference to stratigraphic unit is stale."""
    pass


# ============================================================================
# Domain Validation Exception (for backward compatibility)
# ============================================================================

class DomainValidationError(ValidationError):
    """
    Domain-specific validation error.
    
    This is kept for backward compatibility but new code should use
    more specific exception types.
    """
    pass


# ============================================================================
# Business Logic Exception (for backward compatibility)
# ============================================================================

class BusinessLogicError(DomainException):
    """
    Generic business logic error.
    
    This is kept for backward compatibility but new code should use
    more specific exception types.
    """
    pass


# ============================================================================
# Exception Mapping to HTTP Status Codes
# ============================================================================

EXCEPTION_STATUS_CODES = {
    # Authentication (401)
    AuthenticationError: 401,
    InvalidCredentialsError: 401,
    UserInactiveError: 401,
    TokenExpiredError: 401,
    TokenInvalidError: 401,
    
    # Authorization (403)
    AuthorizationError: 403,
    InsufficientPermissionsError: 403,
    NoSiteAccessError: 403,
    SiteAccessDeniedError: 403,
    
    # Not Found (404)
    ResourceNotFoundError: 404,
    PhotoNotFoundError: 404,
    SiteNotFoundError: 404,
    StorageNotFoundError: 404,
    
    # Conflict (409)
    ResourceAlreadyExistsError: 409,
    UnitCodeConflict: 409,
    
    # Validation (422)
    ValidationError: 422,
    DomainValidationError: 422,
    InvalidInputError: 422,
    MissingRequiredFieldError: 422,
    InvalidStratigraphicRelation: 422,
    CycleDetectionError: 422,
    UnsupportedImageFormatError: 422,
    InvalidImageError: 422,
    
    # Storage Full (507)
    StorageFullError: 507,
    
    # Server Error (500)
    DomainException: 500,
    StorageError: 500,
    PhotoServiceError: 500,
    ImageProcessingError: 500,
    HarrisMatrixException: 500,
    BusinessLogicError: 500,
}


def get_status_code(exception: DomainException) -> int:
    """
    Get HTTP status code for a domain exception.
    
    Args:
        exception: Domain exception instance
        
    Returns:
        HTTP status code
    """
    # Try exact match first
    exception_type = type(exception)
    if exception_type in EXCEPTION_STATUS_CODES:
        return EXCEPTION_STATUS_CODES[exception_type]
    
    # Try parent classes
    for exc_class, status_code in EXCEPTION_STATUS_CODES.items():
        if isinstance(exception, exc_class):
            return status_code
    
    # Default to 500
    return 500