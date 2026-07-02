"""
Validation utilities
- Common normalization (normalize_text), vector normalization wrappers
- File validator helpers (size/MIME)
- Password complexity validation
- Query and commitment data validation
"""

import re
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import current_app


def normalize_text(text: str) -> str:
    if not text:
        return ''
    return re.sub(r"\s+", " ", text).strip().lower()


def is_allowed_extension(filename: str, allowed: set[str]) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed


def validate_password(password: str) -> tuple[bool, str | None]:
    """
    Validate password complexity.
    Returns (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    return True, None


def validate_file_mime(file, allowed_mimes: set) -> tuple[bool, str | None]:
    """
    Validate file type using file extension (simplified approach without magic library).
    Returns (is_valid, error_message)
    """
    # Get filename for extension check
    filename = getattr(file, 'filename', '') or ''
    
    if not filename:
        return False, "No filename provided"
    
    # Extract file extension
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    # Map extensions to MIME types
    extension_to_mime = {
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xlsm': 'application/vnd.ms-excel.sheet.macroEnabled.12',
        'xls': 'application/vnd.ms-excel',
        'csv': 'text/csv',
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword'
    }
    
    # Get MIME type for extension
    file_mime = extension_to_mime.get(ext)
    
    if not file_mime:
        return False, f"Unsupported file extension: .{ext}"
    
    # Check if MIME type is in allowed list
    if file_mime in allowed_mimes:
        return True, None
    
    return False, f"File type .{ext} is not allowed"


def validate_file_size(file, max_size: int) -> tuple[bool, str | None]:
    """
    Validate file size.
    Returns (is_valid, error_message)
    """
    if hasattr(file, 'content_length') and file.content_length:
        if file.content_length > max_size:
            return False, f"File size exceeds maximum allowed size of {max_size / (1024*1024):.1f} MB"
    
    # Also check actual file size if available
    if hasattr(file, 'seek') and hasattr(file, 'tell'):
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > max_size:
            return False, f"File size exceeds maximum allowed size of {max_size / (1024*1024):.1f} MB"
    
    return True, None


def validate_query_data(data: Dict[str, Any]) -> Optional[List[str]]:
    """
    Validate query data for creation/update
    
    Args:
        data: Dictionary containing query data
        
    Returns:
        List of validation errors, or None if valid
    """
    errors = []
    
    # Required fields
    required_fields = ['query_description']
    for field in required_fields:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    
    # Validate query_description
    if 'query_description' in data:
        query_desc = data['query_description']
        if not isinstance(query_desc, str):
            errors.append("query_description must be a string")
        elif len(query_desc.strip()) < 10:
            errors.append("query_description must be at least 10 characters long")
        elif len(query_desc) > 10000:
            errors.append("query_description must be less than 10,000 characters")
    
    # Validate state_name
    if 'state_name' in data:
        state_name = data['state_name']
        if not isinstance(state_name, str):
            errors.append("state_name must be a string")
        elif len(state_name.strip()) < 2:
            errors.append("state_name must be at least 2 characters long")
        elif len(state_name) > 100:
            errors.append("state_name must be less than 100 characters")
    
    # Validate assigned_official_email
    if 'assigned_official_email' in data and data['assigned_official_email']:
        email = data['assigned_official_email']
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            errors.append("assigned_official_email must be a valid email address")
    
    # Validate date_received
    if 'date_received' in data:
        date_str = data['date_received']
        if isinstance(date_str, str):
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                errors.append("date_received must be in YYYY-MM-DD format")
        elif isinstance(date_str, datetime):
            # Valid datetime object
            pass
        else:
            errors.append("date_received must be a valid date")
    
    # Validate priority
    if 'priority' in data:
        valid_priorities = ['low', 'medium', 'high', 'critical']
        if data['priority'] not in valid_priorities:
            errors.append(f"priority must be one of: {', '.join(valid_priorities)}")
    
    # Validate status
    if 'status' in data:
        valid_statuses = ['received', 'in_progress', 'awaiting_response', 'responded', 'closed', 'escalated']
        if data['status'] not in valid_statuses:
            errors.append(f"status must be one of: {', '.join(valid_statuses)}")
    
    return errors if errors else None


def validate_commitment_data(data: Dict[str, Any]) -> Optional[List[str]]:
    """
    Validate commitment data for creation/update
    
    Args:
        data: Dictionary containing commitment data
        
    Returns:
        List of validation errors, or None if valid
    """
    errors = []
    
    # Required fields
    required_fields = ['commitment_text', 'audit_query_id']
    for field in required_fields:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    
    # Validate commitment_text
    if 'commitment_text' in data:
        text = data['commitment_text']
        if not isinstance(text, str):
            errors.append("commitment_text must be a string")
        elif len(text.strip()) < 5:
            errors.append("commitment_text must be at least 5 characters long")
        elif len(text) > 2000:
            errors.append("commitment_text must be less than 2,000 characters")
    
    # Validate audit_query_id
    if 'audit_query_id' in data:
        query_id = data['audit_query_id']
        if not isinstance(query_id, int) or query_id <= 0:
            errors.append("audit_query_id must be a positive integer")
    
    # Validate target_date
    if 'target_date' in data and data['target_date']:
        date_str = data['target_date']
        if isinstance(date_str, str):
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                # Check if date is in the future
                if target_date < datetime.utcnow().date():
                    errors.append("target_date must be in the future")
            except ValueError:
                errors.append("target_date must be in YYYY-MM-DD format")
        elif isinstance(date_str, datetime):
            if date_str.date() < datetime.utcnow().date():
                errors.append("target_date must be in the future")
    
    # Validate commitment_type
    if 'commitment_type' in data:
        valid_types = ['rectification', 'implementation', 'policy_change', 'system_enhancement', 'investigation', 'procurement', 'general']
        if data['commitment_type'] not in valid_types:
            errors.append(f"commitment_type must be one of: {', '.join(valid_types)}")
    
    # Validate status
    if 'status' in data:
        valid_statuses = ['pending', 'in_progress', 'completed', 'overdue', 'cancelled']
        if data['status'] not in valid_statuses:
            errors.append(f"status must be one of: {', '.join(valid_statuses)}")
    
    # Validate verification_method
    if 'verification_method' in data:
        valid_methods = ['automated_testing', 'manual_review', 'document_review', 'user_acceptance_testing', 'peer_review', 'vendor_confirmation', 'manual_verification']
        if data['verification_method'] not in valid_methods:
            errors.append(f"verification_method must be one of: {', '.join(valid_methods)}")
    
    return errors if errors else None
