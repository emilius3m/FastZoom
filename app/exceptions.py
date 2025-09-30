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