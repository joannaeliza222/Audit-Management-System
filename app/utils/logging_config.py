"""
Structured logging configuration for AMS
"""
import os
import logging
import logging.handlers
import structlog
from datetime import datetime
from typing import Any, Dict
from flask import Flask, request, g
from flask import current_app


class RequestIdFilter(logging.Filter):
    """Filter to add request ID to log records"""
    
    def filter(self, record):
        try:
            record.request_id = getattr(g, 'request_id', 'no-request-id')
            record.user_id = getattr(g, 'user_id', 'anonymous')
            record.ip_address = getattr(request, 'remote_addr', 'unknown') if request else 'unknown'
        except RuntimeError:
            # Working outside of application context
            record.request_id = 'no-context'
            record.user_id = 'anonymous'
            record.ip_address = 'unknown'
        return True


def setup_logging(app: Flask):
    """Setup structured logging for the application"""
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Setup formatters
    json_formatter = logging.Formatter(
        '%(asctime)s %(name)s %(levelname)s %(request_id)s %(user_id)s %(ip_address)s %(message)s'
    )
    
    detailed_formatter = logging.Formatter(
        '%(asctime)s %(name)s %(levelname)s [%(request_id)s] [%(user_id)s] [%(ip_address)s] %(message)s [in %(pathname)s:%(lineno)d]'
    )
    
    # File handler for all logs
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/ams.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(logging.INFO)
    file_handler.addFilter(RequestIdFilter())
    
    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        'logs/ams-errors.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setFormatter(json_formatter)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(RequestIdFilter())
    
    # Console handler for development
    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(detailed_formatter)
        console_handler.setLevel(logging.DEBUG)
        console_handler.addFilter(RequestIdFilter())
        app.logger.addHandler(console_handler)
    
    # Add handlers to app logger
    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_handler)
    
    # Set log level
    if app.debug:
        app.logger.setLevel(logging.DEBUG)
    else:
        app.logger.setLevel(logging.INFO)
    
    # Configure other loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    app.logger.info('Logging configured successfully')


def log_request_info():
    """Log request information"""
    try:
        if request:
            current_app.logger.info(
                'Request started',
                extra={
                    'method': request.method,
                    'url': request.url,
                    'user_agent': str(request.user_agent),
                    'content_length': request.content_length
                }
            )
    except RuntimeError:
        # Working outside of application context
        pass


def log_response_info(response):
    """Log response information"""
    try:
        if request:
            current_app.logger.info(
                'Request completed',
                extra={
                    'status_code': response.status_code,
                    'content_length': response.content_length
                }
            )
    except RuntimeError:
        # Working outside of application context
        pass
    return response


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)


class SecurityLogger:
    """Specialized logger for security events"""
    
    def __init__(self):
        self.logger = get_logger('security')
    
    def log_login_attempt(self, username: str, success: bool, ip_address: str = None):
        """Log login attempt"""
        try:
            self.logger.info(
                'login_attempt',
                username=username,
                success=success,
                ip_address=ip_address,
                timestamp=datetime.utcnow().isoformat()
            )
        except RuntimeError:
            # Working outside of application context
            pass
    
    def log_permission_denied(self, user_id: str, resource: str, action: str):
        """Log permission denied event"""
        try:
            self.logger.warning(
                'permission_denied',
                user_id=user_id,
                resource=resource,
                action=action,
                timestamp=datetime.utcnow().isoformat()
            )
        except RuntimeError:
            # Working outside of application context
            pass
    
    def log_suspicious_activity(self, description: str, details: Dict[str, Any] = None):
        """Log suspicious activity"""
        try:
            self.logger.error(
                'suspicious_activity',
                description=description,
                details=details or {},
                timestamp=datetime.utcnow().isoformat()
            )
        except RuntimeError:
            # Working outside of application context
            pass
    
    def log_file_upload(self, user_id: str, filename: str, file_type: str, size: int):
        """Log file upload event"""
        try:
            self.logger.info(
                'file_upload',
                user_id=user_id,
                filename=filename,
                file_type=file_type,
                size=size,
                timestamp=datetime.utcnow().isoformat()
            )
        except RuntimeError:
            # Working outside of application context
            pass


class AuditLogger:
    """Specialized logger for audit events"""
    
    def __init__(self):
        self.logger = get_logger('audit')
    
    def log_data_change(self, user_id: str, table: str, record_id: str, action: str, changes: Dict[str, Any] = None):
        """Log data modification"""
        try:
            self.logger.info(
                'data_change',
                user_id=user_id,
                table=table,
                record_id=record_id,
                action=action,
                changes=changes or {},
                timestamp=datetime.utcnow().isoformat()
            )
        except RuntimeError:
            # Working outside of application context
            pass
    
    def log_bulk_operation(self, user_id: str, operation: str, count: int, details: Dict[str, Any] = None):
        """Log bulk operations"""
        try:
            self.logger.info(
                'bulk_operation',
                user_id=user_id,
                operation=operation,
                count=count,
                details=details or {},
                timestamp=datetime.utcnow().isoformat()
            )
        except RuntimeError:
            # Working outside of application context
            pass


# Global logger instances
security_logger = SecurityLogger()
audit_logger = AuditLogger()
