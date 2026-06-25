"""
Centralized error handling for AMS
"""
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from flask import jsonify, current_app, request, g
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DatabaseError
from marshmallow import ValidationError
from .logging_config import get_logger, security_logger

logger = get_logger(__name__)


class AMSError(Exception):
    """Base exception class for AMS application"""
    
    def __init__(self, message: str, error_code: str = None, status_code: int = 500, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.status_code = status_code
        self.details = details or {}


class ValidationError(AMSError):
    """Raised when input validation fails"""
    
    def __init__(self, message: str, field: str = None, details: Dict[str, Any] = None):
        super().__init__(message, "VALIDATION_ERROR", 400, details)
        self.field = field


class AuthenticationError(AMSError):
    """Raised when authentication fails"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTHENTICATION_ERROR", 401)


class AuthorizationError(AMSError):
    """Raised when user lacks permission"""
    
    def __init__(self, message: str = "Access denied", resource: str = None, action: str = None):
        details = {}
        if resource:
            details['resource'] = resource
        if action:
            details['action'] = action
        super().__init__(message, "AUTHORIZATION_ERROR", 403, details)


class NotFoundError(AMSError):
    """Raised when resource is not found"""
    
    def __init__(self, message: str = "Resource not found", resource_type: str = None):
        details = {}
        if resource_type:
            details['resource_type'] = resource_type
        super().__init__(message, "NOT_FOUND_ERROR", 404, details)


class ConflictError(AMSError):
    """Raised when resource conflict occurs"""
    
    def __init__(self, message: str = "Resource conflict", details: Dict[str, Any] = None):
        super().__init__(message, "CONFLICT_ERROR", 409, details)


class RateLimitError(AMSError):
    """Raised when rate limit is exceeded"""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = None):
        details = {}
        if retry_after:
            details['retry_after'] = retry_after
        super().__init__(message, "RATE_LIMIT_ERROR", 429, details)


class FileUploadError(AMSError):
    """Raised when file upload fails"""
    
    def __init__(self, message: str, file_type: str = None, details: Dict[str, Any] = None):
        details = details or {}
        if file_type:
            details['file_type'] = file_type
        super().__init__(message, "FILE_UPLOAD_ERROR", 400, details)


class DatabaseError(AMSError):
    """Raised when database operation fails"""
    
    def __init__(self, message: str = "Database operation failed", operation: str = None):
        details = {}
        if operation:
            details['operation'] = operation
        super().__init__(message, "DATABASE_ERROR", 500, details)


def create_error_response(error: AMSError, include_traceback: bool = False) -> Dict[str, Any]:
    """Create standardized error response"""
    response = {
        'error': {
            'code': error.error_code,
            'message': error.message,
            'status_code': error.status_code,
            'timestamp': datetime.utcnow().isoformat(),
            'request_id': getattr(g, 'request_id', None)
        }
    }
    
    if error.details:
        response['error']['details'] = error.details
    
    if include_traceback and current_app.debug:
        response['error']['traceback'] = traceback.format_exc()
    
    return response


def handle_ams_error(error: AMSError):
    """Handle AMS application errors"""
    logger.error(
        f"AMS Error: {error.error_code}",
        error_code=error.error_code,
        message=error.message,
        status_code=error.status_code,
        details=error.details,
        request_id=getattr(g, 'request_id', None)
    )
    
    response = create_error_response(error, include_traceback=current_app.debug)
    return jsonify(response), error.status_code


def handle_http_exception(error: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(
        f"HTTP Exception: {error.code}",
        error_code=error.code,
        message=error.description,
        request_id=getattr(g, 'request_id', None)
    )
    
    ams_error = AMSError(
        message=error.description or "HTTP Error",
        error_code=f"HTTP_{error.code}",
        status_code=error.code
    )
    
    response = create_error_response(ams_error, include_traceback=current_app.debug)
    return jsonify(response), error.code


def handle_sqlalchemy_error(error: SQLAlchemyError):
    """Handle SQLAlchemy errors"""
    logger.error(
        "Database error occurred",
        error_type=type(error).__name__,
        error_message=str(error),
        request_id=getattr(g, 'request_id', None)
    )
    
    if isinstance(error, IntegrityError):
        ams_error = ConflictError("Data integrity violation", {
            'type': 'integrity_error',
            'details': str(error.orig) if hasattr(error, 'orig') else None
        })
    elif isinstance(error, DatabaseError):
        ams_error = DatabaseError("Database operation failed", {
            'type': 'database_error',
            'details': str(error.orig) if hasattr(error, 'orig') else None
        })
    else:
        ams_error = DatabaseError("Unexpected database error")
    
    response = create_error_response(ams_error, include_traceback=current_app.debug)
    return jsonify(response), ams_error.status_code


def handle_validation_error(error: ValidationError):
    """Handle Marshmallow validation errors"""
    logger.warning(
        "Validation error occurred",
        validation_errors=error.messages,
        request_id=getattr(g, 'request_id', None)
    )
    
    ams_error = ValidationError("Input validation failed", details=error.messages)
    response = create_error_response(ams_error, include_traceback=current_app.debug)
    return jsonify(response), ams_error.status_code


def handle_generic_error(error: Exception):
    """Handle unexpected errors"""
    logger.exception(
        "Unexpected error occurred",
        error_type=type(error).__name__,
        error_message=str(error),
        request_id=getattr(g, 'request_id', None)
    )
    
    ams_error = AMSError("Internal server error")
    response = create_error_response(ams_error, include_traceback=current_app.debug)
    return jsonify(response), ams_error.status_code


def register_error_handlers(app):
    """Register all error handlers with the Flask app"""
    
    # AMS application errors
    app.register_error_handler(AMSError, handle_ams_error)
    
    # HTTP exceptions
    app.register_error_handler(HTTPException, handle_http_exception)
    
    # Database errors
    app.register_error_handler(SQLAlchemyError, handle_sqlalchemy_error)
    
    # Validation errors
    app.register_error_handler(ValidationError, handle_validation_error)
    
    # Generic exceptions
    app.register_error_handler(Exception, handle_generic_error)


def log_security_event(event_type: str, message: str, details: Dict[str, Any] = None):
    """Log security-related events"""
    security_logger.log_suspicious_activity(message, {
        'event_type': event_type,
        'details': details or {},
        'request_id': getattr(g, 'request_id', None),
        'ip_address': getattr(g, 'ip_address', None)
    })


class ErrorContext:
    """Context manager for error handling"""
    
    def __init__(self, operation: str, reraise: bool = True):
        self.operation = operation
        self.reraise = reraise
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        
        if exc_type is None:
            logger.info(
                f"Operation completed successfully: {self.operation}",
                operation=self.operation,
                duration=duration,
                request_id=getattr(g, 'request_id', None)
            )
        else:
            logger.error(
                f"Operation failed: {self.operation}",
                operation=self.operation,
                duration=duration,
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                request_id=getattr(g, 'request_id', None)
            )
            
            if not self.reraise:
                return True  # Suppress the exception
        
        return False


def safe_execute(operation: str, func, *args, **kwargs):
    """Safely execute a function with error handling"""
    with ErrorContext(operation, reraise=False):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, AMSError):
                raise
            else:
                raise DatabaseError(f"Operation '{operation}' failed", operation)
