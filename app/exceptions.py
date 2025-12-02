"""Custom exceptions for the application."""


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


class HarrisMatrixValidationError(BusinessLogicError):
    """Exception for Harris Matrix validation errors."""
    
    def __init__(self, message: str, field: str = None):
        """
        Initialize Harris Matrix validation error.
        
        Args:
            message: Error message
            field: Field that caused the validation error
        """
        super().__init__(message, status_code=422)
        self.field = field


class StratigraphicCycleDetected(BusinessLogicError):
    """Exception raised when cycles are detected in stratigraphic relationships."""
    
    def __init__(self, cycle_path: list = None):
        """
        Initialize stratigraphic cycle error.
        
        Args:
            cycle_path: List of unit codes that form the cycle
        """
        message = "Ciclo stratigrafico rilevato nelle relazioni"
        if cycle_path:
            message += f": {' -> '.join(cycle_path)}"
        
        super().__init__(message, status_code=422)
        self.cycle_path = cycle_path


class UnitCodeConflict(BusinessLogicError):
    """Exception raised when unit code conflicts occur."""
    
    def __init__(self, code: str, unit_type: str = None):
        """
        Initialize unit code conflict error.
        
        Args:
            code: Conflicting unit code
            unit_type: Type of unit ('us' or 'usm')
        """
        prefix = f"{unit_type.upper()}:" if unit_type else "Unità"
        message = f"{prefix} Il codice '{code}' esiste già in questo sito"
        super().__init__(message, status_code=409)
        self.code = code
        self.unit_type = unit_type


class InvalidStratigraphicRelation(BusinessLogicError):
    """Exception raised for invalid stratigraphic relationships."""
    
    def __init__(self, relation_type: str, from_unit: str = None, to_unit: str = None, reason: str = None):
        """
        Initialize invalid relation error.
        
        Args:
            relation_type: Type of relationship that is invalid
            from_unit: Source unit code
            to_unit: Target unit code
            reason: Explanation of why the relationship is invalid
        """
        message = f"Relazione stratigrafica non valida: {relation_type}"
        if from_unit and to_unit:
            message += f" da {from_unit} a {to_unit}"
        if reason:
            message += f" - {reason}"
        
        super().__init__(message, status_code=422)
        self.relation_type = relation_type
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.reason = reason


class HarrisMatrixServiceError(BusinessLogicError):
    """Exception for general Harris Matrix service errors."""
    
    def __init__(self, message: str, operation: str = None):
        """
        Initialize Harris Matrix service error.
        
        Args:
            message: Error message
            operation: Operation that failed
        """
        if operation:
            message = f"Errore durante l'operazione '{operation}': {message}"
        
        super().__init__(message, status_code=500)
        self.operation = operation