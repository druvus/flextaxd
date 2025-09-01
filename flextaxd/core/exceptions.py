"""FlexTaxD custom exceptions."""

from typing import Optional, Any


class FlexTaxDError(Exception):
    """Base exception for all FlexTaxD errors."""
    
    def __init__(self, message: str, context: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}


class DatabaseError(FlexTaxDError):
    """Database-related errors."""
    pass


class ParseError(FlexTaxDError):
    """Parsing-related errors."""
    pass


class ValidationError(FlexTaxDError):
    """Input validation errors."""
    pass


class ExportError(FlexTaxDError):
    """Export-related errors."""
    pass


class ConfigurationError(FlexTaxDError):
    """Configuration-related errors."""
    pass


class FileOperationError(FlexTaxDError):
    """File I/O related errors."""
    pass