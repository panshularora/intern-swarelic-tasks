class SCAIAPIError(Exception):
    """Base exception for all SCAI API errors."""
    def __init__(self, message: str, status_code: int = None, response_body: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SCAIAuthError(SCAIAPIError):
    """Raised on 401/403 responses."""
    pass


class SCAINotFoundError(SCAIAPIError):
    """Raised on 404 responses."""
    pass


class SCAIValidationError(SCAIAPIError):
    """Raised on 400 responses with field-level validation errors."""
    def __init__(self, message: str, errors: dict):
        super().__init__(message, 400, errors)
        self.errors = errors
