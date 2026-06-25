"""
Input validation and sanitization utilities for AMS
"""
import re
import html
import bleach
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
from flask import request
from marshmallow import Schema, fields, validate, validates, ValidationError
from .error_handlers import ValidationError as AMSError
from .logging_config import get_logger

logger = get_logger(__name__)


# HTML sanitization configuration
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'blockquote', 'code', 'pre'
]

ALLOWED_ATTRIBUTES = {
    '*': ['class'],
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'width', 'height'],
}

ALLOWED_STYLES = [
    'color', 'background-color', 'font-weight', 'font-style',
    'text-decoration', 'text-align'
]


class InputSanitizer:
    """Utility class for sanitizing user inputs"""
    
    @staticmethod
    def sanitize_html(content: str) -> str:
        """Sanitize HTML content to prevent XSS"""
        if not content:
            return ""
        
        try:
            # First, unescape any existing HTML entities
            content = html.unescape(content)
            
            # Clean with bleach
            cleaned = bleach.clean(
                content,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                styles=ALLOWED_STYLES,
                strip=True
            )
            
            return cleaned.strip()
        except Exception as e:
            logger.warning(f"HTML sanitization failed: {e}")
            return ""
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = None) -> str:
        """Sanitize plain text input"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Unescape HTML entities
        text = html.unescape(text)
        
        # Remove control characters except newlines and tabs
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Trim whitespace
        text = text.strip()
        
        # Apply length limit
        if max_length and len(text) > max_length:
            text = text[:max_length]
            logger.warning(f"Text truncated to {max_length} characters")
        
        return text
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent directory traversal"""
        if not filename:
            return ""
        
        # Remove directory separators
        filename = filename.replace('/', '_').replace('\\', '_')
        
        # Remove control characters
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        
        # Remove dangerous characters
        filename = re.sub(r'[<>:"|?*]', '', filename)
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            name = name[:255-len(ext)-1] if ext else name[:255]
            filename = f"{name}.{ext}" if ext else name
        
        return filename.strip()
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format and safety"""
        if not url:
            return False
        
        try:
            parsed = urlparse(url)
            
            # Check scheme
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Check for dangerous patterns
            dangerous_patterns = [
                'javascript:', 'data:', 'vbscript:', 'file:', 'ftp:'
            ]
            
            url_lower = url.lower()
            for pattern in dangerous_patterns:
                if pattern in url_lower:
                    return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def sanitize_email(email: str) -> str:
        """Sanitize and validate email address"""
        if not email:
            return ""
        
        email = email.strip().lower()
        
        # Basic email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise AMSError("Invalid email format", "VALIDATION_ERROR")
        
        return email
    
    @staticmethod
    def sanitize_phone(phone: str) -> str:
        """Sanitize phone number"""
        if not phone:
            return ""
        
        # Remove all non-digit characters
        phone = re.sub(r'[^\d+]', '', phone)
        
        # Basic validation
        if len(phone) < 10 or len(phone) > 15:
            raise AMSError("Invalid phone number format", "VALIDATION_ERROR")
        
        return phone


class ValidationSchema(Schema):
    """Base schema for common validation patterns"""
    
    # Common field validators
    text_field = fields.Str(
        validate=validate.Length(min=1, max=1000),
        required=True
    )
    
    email_field = fields.Email(
        validate=validate.Length(max=254),
        required=True
    )
    
    optional_text_field = fields.Str(
        validate=validate.Length(max=1000),
        required=False,
        allow_none=True
    )
    
    id_field = fields.Int(
        validate=validate.Range(min=1),
        required=True
    )
    
    state_field = fields.Str(
        validate=validate.OneOf([
            'Andaman and Nicobar Islands', 'Andhra Pradesh', 'Arunachal Pradesh',
            'Assam', 'Bihar', 'Chandigarh', 'Chhattisgarh', 'Dadra and Nagar Haveli',
            'Daman and Diu', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh',
            'Jammu and Kashmir', 'Jharkhand', 'Karnataka', 'Kerala', 'Lakshadweep',
            'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram',
            'Nagaland', 'Odisha', 'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim',
            'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand',
            'West Bengal'
        ]),
        required=True
    )


class FAQValidationSchema(ValidationSchema):
    """Schema for FAQ validation"""
    
    question = fields.Str(
        validate=validate.Length(min=5, max=1000),
        required=True
    )
    
    answer = fields.Str(
        validate=validate.Length(min=10, max=10000),
        required=True
    )
    
    category = fields.Str(
        validate=validate.Length(max=100),
        required=False,
        allow_none=True
    )
    
    tags = fields.List(
        fields.Str(validate=validate.Length(max=50)),
        required=False,
        allow_none=True
    )
    
    @validates('question')
    def validate_question(self, value):
        """Validate question content"""
        # Check for potential XSS patterns
        if '<script' in value.lower() or 'javascript:' in value.lower():
            raise ValidationError("Question contains potentially unsafe content")
    
    @validates('answer')
    def validate_answer(self, value):
        """Validate answer content"""
        # Check for potential XSS patterns
        if '<script' in value.lower() or 'javascript:' in value.lower():
            raise ValidationError("Answer contains potentially unsafe content")


class UserValidationSchema(ValidationSchema):
    """Schema for user validation"""
    
    username = fields.Str(
        validate=validate.Length(min=3, max=50),
        required=True
    )
    
    email = fields.Email(
        validate=validate.Length(max=254),
        required=True
    )
    
    full_name = fields.Str(
        validate=validate.Length(min=2, max=100),
        required=True
    )
    
    state = fields.Str(
        validate=validate.OneOf([
            'Andaman and Nicobar Islands', 'Andhra Pradesh', 'Arunachal Pradesh',
            'Assam', 'Bihar', 'Chandigarh', 'Chhattisgarh', 'Dadra and Nagar Haveli',
            'Daman and Diu', 'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh',
            'Jammu and Kashmir', 'Jharkhand', 'Karnataka', 'Kerala', 'Lakshadweep',
            'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram',
            'Nagaland', 'Odisha', 'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim',
            'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand',
            'West Bengal'
        ]),
        required=True
    )
    
    @validates('username')
    def validate_username(self, value):
        """Validate username format"""
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            raise ValidationError("Username can only contain letters, numbers, and underscores")


class InputValidator:
    """Main input validation class"""
    
    def __init__(self):
        self.faq_schema = FAQValidationSchema()
        self.user_schema = UserValidationSchema()
        self.sanitizer = InputSanitizer()
    
    def validate_faq_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate FAQ data"""
        try:
            # Sanitize inputs first
            sanitized_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    if key in ['question', 'answer']:
                        sanitized_data[key] = self.sanitizer.sanitize_html(value)
                    else:
                        sanitized_data[key] = self.sanitizer.sanitize_text(value)
                else:
                    sanitized_data[key] = value
            
            # Validate with schema
            validated_data = self.faq_schema.load(sanitized_data)
            return validated_data
            
        except ValidationError as e:
            logger.warning(f"FAQ validation failed: {e.messages}")
            raise AMSError("Invalid FAQ data", "VALIDATION_ERROR", e.messages)
        except Exception as e:
            logger.error(f"Unexpected error during FAQ validation: {e}")
            raise AMSError("Validation failed", "VALIDATION_ERROR")
    
    def validate_user_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user data"""
        try:
            # Sanitize inputs first
            sanitized_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    if key == 'email':
                        sanitized_data[key] = self.sanitizer.sanitize_email(value)
                    else:
                        sanitized_data[key] = self.sanitizer.sanitize_text(value)
                else:
                    sanitized_data[key] = value
            
            # Validate with schema
            validated_data = self.user_schema.load(sanitized_data)
            return validated_data
            
        except ValidationError as e:
            logger.warning(f"User validation failed: {e.messages}")
            raise AMSError("Invalid user data", "VALIDATION_ERROR", e.messages)
        except Exception as e:
            logger.error(f"Unexpected error during user validation: {e}")
            raise AMSError("Validation failed", "VALIDATION_ERROR")
    
    def validate_search_query(self, query: str) -> str:
        """Validate and sanitize search query"""
        if not query:
            return ""
        
        # Sanitize query
        sanitized_query = self.sanitizer.sanitize_text(query, max_length=500)
        
        # Check for SQL injection patterns
        sql_patterns = [
            r'union\s+select', r'insert\s+into', r'delete\s+from',
            r'drop\s+table', r'create\s+table', r'update\s+.*set',
            r'exec\s*\(', r'script\s*>', r'--', r'/\*.*\*/'
        ]
        
        query_lower = sanitized_query.lower()
        for pattern in sql_patterns:
            if re.search(pattern, query_lower):
                logger.warning(f"Potential SQL injection in search query: {query}")
                raise AMSError("Invalid search query", "VALIDATION_ERROR")
        
        return sanitized_query
    
    def validate_file_upload(self, filename: str, content_type: str, size: int) -> Dict[str, Any]:
        """Validate file upload"""
        try:
            # Sanitize filename
            safe_filename = self.sanitizer.sanitize_filename(filename)
            
            if not safe_filename:
                raise AMSError("Invalid filename", "FILE_UPLOAD_ERROR")
            
            # Check file extension
            allowed_extensions = ['xlsx', 'xls', 'csv', 'pdf', 'doc', 'docx']
            file_ext = safe_filename.rsplit('.', 1)[-1].lower() if '.' in safe_filename else ''
            
            if file_ext not in allowed_extensions:
                raise AMSError(f"File type '{file_ext}' not allowed", "FILE_UPLOAD_ERROR")
            
            # Check file size (default 50MB limit)
            max_size = 50 * 1024 * 1024  # 50MB
            if size > max_size:
                raise AMSError(f"File size exceeds maximum limit of {max_size // (1024*1024)}MB", "FILE_UPLOAD_ERROR")
            
            return {
                'filename': safe_filename,
                'extension': file_ext,
                'size': size,
                'content_type': content_type
            }
            
        except AMSError:
            raise
        except Exception as e:
            logger.error(f"File validation error: {e}")
            raise AMSError("File validation failed", "FILE_UPLOAD_ERROR")


# Global validator instance
validator = InputValidator()


def validate_input(schema_class, data: Dict[str, Any]) -> Dict[str, Any]:
    """Generic input validation function"""
    try:
        schema = schema_class()
        return schema.load(data)
    except ValidationError as e:
        logger.warning(f"Validation failed: {e.messages}")
        raise AMSError("Invalid input data", "VALIDATION_ERROR", e.messages)
    except Exception as e:
        logger.error(f"Unexpected validation error: {e}")
        raise AMSError("Validation failed", "VALIDATION_ERROR")


def sanitize_input(text: str, max_length: int = None) -> str:
    """Simple input sanitization function"""
    if not text:
        return ""
    
    sanitizer = InputSanitizer()
    return sanitizer.sanitize_text(text, max_length)


def validate_file_upload(filename: str, content_type: str, size: int) -> Dict[str, Any]:
    """Validate file upload - standalone function"""
    validator = InputValidator()
    return validator.validate_file_upload(filename, content_type, size)


def sanitize_request_data() -> Dict[str, Any]:
    """Sanitize request data"""
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = request.form.to_dict()
    
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = InputSanitizer.sanitize_text(value)
        else:
            sanitized[key] = value
    
    return sanitized
