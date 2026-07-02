import os
import re
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import current_app, request
from werkzeug.security import generate_password_hash, check_password_hash
import ipaddress

from app import db
from app.models import User, FailedLoginAttempt


class SecurityService:
    """Enhanced security service for complete local operation"""
    
    def __init__(self):
        self.max_failed_attempts = 5
        self.lockout_duration_minutes = 15
        self.session_timeout_hours = 8
        self.password_min_length = 12
        self.password_require_special = True
        self.password_require_numbers = True
        self.password_require_uppercase = True
        
    def validate_password_strength(self, password: str) -> Tuple[bool, List[str]]:
        """Validate password strength according to security policy"""
        errors = []
        
        if len(password) < self.password_min_length:
            errors.append(f"Password must be at least {self.password_min_length} characters long")
        
        if self.password_require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self.password_require_numbers and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")
        
        if self.password_require_special and not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            errors.append("Password must contain at least one special character")
        
        # Check for common weak passwords
        weak_passwords = [
            'password', '123456', 'password123', 'admin', 'letmein',
            'welcome', 'monkey', 'dragon', 'master', 'sunshine'
        ]
        if password.lower() in weak_passwords:
            errors.append("Password is too common and weak")
        
        return len(errors) == 0, errors
    
    def check_account_lockout(self, email: str, ip_address: str) -> Tuple[bool, Optional[int]]:
        """Check if account is locked due to failed attempts"""
        recent_failures = FailedLoginAttempt.query.filter(
            FailedLoginAttempt.email == email,
            FailedLoginAttempt.attempt_time > datetime.utcnow() - timedelta(minutes=self.lockout_duration_minutes),
            FailedLoginAttempt.success == False
        ).count()
        
        if recent_failures >= self.max_failed_attempts:
            # Get the time of the last failed attempt
            last_failure = FailedLoginAttempt.query.filter(
                FailedLoginAttempt.email == email,
                FailedLoginAttempt.success == False
            ).order_by(FailedLoginAttempt.attempt_time.desc()).first()
            
            if last_failure:
                remaining_minutes = self.lockout_duration_minutes - int(
                    (datetime.utcnow() - last_failure.attempt_time).total_seconds() / 60
                )
                return True, max(0, remaining_minutes)
        
        return False, None
    
    def record_login_attempt(self, email: str, success: bool, ip_address: str):
        """Record login attempt for security monitoring"""
        attempt = FailedLoginAttempt(
            email=email,
            ip_address=ip_address,
            attempt_time=datetime.utcnow(),
            success=success
        )
        
        db.session.add(attempt)
        
        # Clean up old attempts (older than 30 days)
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        FailedLoginAttempt.query.filter(
            FailedLoginAttempt.attempt_time < cutoff_date
        ).delete()
        
        db.session.commit()
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP address is allowed (for IP whitelisting if configured)"""
        # Get allowed IP ranges from environment variable
        allowed_ips = current_app.config.get('ALLOWED_IP_RANGES', '')
        
        if not allowed_ips:
            return True  # No IP restrictions configured
        
        try:
            allowed_ranges = [ip.strip() for ip in allowed_ips.split(',')]
            client_ip = ipaddress.ip_address(ip_address)
            
            for ip_range in allowed_ranges:
                if '/' in ip_range:
                    # CIDR notation
                    network = ipaddress.ip_network(ip_range, strict=False)
                    if client_ip in network:
                        return True
                else:
                    # Single IP
                    if client_ip == ipaddress.ip_address(ip_range):
                        return True
            
            return False
            
        except Exception as e:
            current_app.logger.error(f"IP validation error: {str(e)}")
            return True  # Allow access if validation fails
    
    def validate_session_integrity(self, session_data: Dict) -> bool:
        """Validate session integrity and detect tampering"""
        required_fields = ['user_id', 'role', 'login_time']
        
        # Check required fields
        for field in required_fields:
            if field not in session_data:
                return False
        
        # Check session age
        try:
            login_time = session_data['login_time']
            if isinstance(login_time, str):
                login_time = datetime.fromisoformat(login_time)
            
            session_age = datetime.utcnow() - login_time
            if session_age > timedelta(hours=self.session_timeout_hours):
                return False
                
        except Exception:
            return False
        
        return True
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate cryptographically secure token"""
        return secrets.token_urlsafe(length)
    
    def hash_sensitive_data(self, data: str) -> str:
        """Hash sensitive data for storage"""
        return hashlib.sha256(data.encode()).hexdigest()
    
    def encrypt_sensitive_field(self, data: str) -> str:
        """Encrypt sensitive field (placeholder for actual encryption)"""
        # In a real implementation, you would use proper encryption
        # For now, we'll just hash it as a placeholder
        return self.hash_sensitive_data(data)
    
    def sanitize_input(self, input_data: str, max_length: int = 1000) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not input_data:
            return ""
        
        # Truncate to max length
        if len(input_data) > max_length:
            input_data = input_data[:max_length]
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']
        for char in dangerous_chars:
            input_data = input_data.replace(char, '')
        
        # Remove script tags and event handlers
        input_data = re.sub(r'<script[^>]*>.*?</script>', '', input_data, flags=re.IGNORECASE | re.DOTALL)
        input_data = re.sub(r'on\w+\s*=', '', input_data, flags=re.IGNORECASE)
        
        return input_data.strip()
    
    def validate_file_upload(self, file_data, allowed_extensions: List[str], 
                           max_size_mb: int = 100) -> Tuple[bool, List[str]]:
        """Validate uploaded file for security"""
        errors = []
        
        # Check file extension
        if file_data and hasattr(file_data, 'filename'):
            filename = file_data.filename
            if not filename:
                errors.append("No filename provided")
                return False, errors
            
            # Check extension
            if '.' not in filename:
                errors.append("File must have an extension")
                return False, errors
            
            extension = filename.rsplit('.', 1)[1].lower()
            if extension not in allowed_extensions:
                errors.append(f"File extension '{extension}' not allowed")
            
            # Check file size
            file_data.seek(0, os.SEEK_END)
            file_size = file_data.tell()
            file_data.seek(0)
            
            max_size_bytes = max_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                errors.append(f"File size exceeds maximum allowed size of {max_size_mb}MB")
            
            # Check file content (basic validation)
            try:
                # Read first few bytes to check file signature
                file_header = file_data.read(1024)
                file_data.seek(0)
                
                # Basic file signature validation
                if extension == 'pdf':
                    if not file_header.startswith(b'%PDF'):
                        errors.append("Invalid PDF file signature")
                elif extension in ['xlsx', 'xls']:
                    if not (file_header.startswith(b'PK\x03\x04') or 
                           file_header.startswith(b'\xd0\xcf\x11\xe0')):
                        errors.append("Invalid Excel file signature")
                elif extension == 'csv':
                    # CSV is text-based, check if it's readable as text
                    try:
                        file_header.decode('utf-8')
                    except UnicodeDecodeError:
                        errors.append("Invalid CSV file format")
                
            except Exception as e:
                errors.append(f"Error reading file: {str(e)}")
        
        return len(errors) == 0, errors
    
    def audit_log_action(self, action: str, user_email: str, details: Dict = None, 
                        ip_address: str = None):
        """Log security-relevant actions for audit trail"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'user_email': user_email,
            'ip_address': ip_address or request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'details': details or {}
        }
        
        # Log to application logger
        current_app.logger.info(f"AUDIT: {log_entry}")
        
        # In a production environment, you might want to:
        # 1. Store in a separate audit log table
        # 2. Send to SIEM system
        # 3. Write to immutable storage
    
    def check_data_privacy_compliance(self, data: Dict) -> Tuple[bool, List[str]]:
        """Check data for privacy compliance issues"""
        violations = []
        
        # Check for PII patterns
        pii_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
            'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
        }
        
        for field_name, field_value in data.items():
            if isinstance(field_value, str):
                for pii_type, pattern in pii_patterns.items():
                    if re.search(pattern, field_value):
                        violations.append(f"Potential {pii_type} found in field '{field_name}'")
        
        # Check for sensitive keywords
        sensitive_keywords = [
            'password', 'secret', 'confidential', 'private', 'sensitive',
            'internal', 'restricted', 'proprietary'
        ]
        
        for field_name, field_value in data.items():
            if isinstance(field_value, str):
                field_lower = field_value.lower()
                for keyword in sensitive_keywords:
                    if keyword in field_lower:
                        violations.append(f"Sensitive keyword '{keyword}' found in field '{field_name}'")
        
        return len(violations) == 0, violations
    
    def generate_security_headers(self) -> Dict[str, str]:
        """Generate security headers for HTTP responses"""
        headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
        }
        
        # Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",  # Remove 'unsafe-inline' in production
            "style-src 'self' 'unsafe-inline'",   # Remove 'unsafe-inline' in production
            "img-src 'self' data: https:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        
        headers['Content-Security-Policy'] = '; '.join(csp_directives)
        
        return headers
    
    def validate_api_key(self, api_key: str) -> bool:
        """Validate API key for API access"""
        # In a real implementation, you would check against stored API keys
        # For now, we'll implement a simple validation based on environment variables
        valid_keys = current_app.config.get('VALID_API_KEYS', '').split(',')
        
        return api_key in valid_keys
    
    def rate_limit_check(self, identifier: str, limit: int, window_minutes: int = 60) -> Tuple[bool, int]:
        """Check rate limiting for API endpoints"""
        # This is a simplified implementation
        # In production, you would use Redis or similar for distributed rate limiting
        
        current_time = datetime.utcnow()
        window_start = current_time - timedelta(minutes=window_minutes)
        
        # Count requests in the window (this would be stored in cache/database)
        # For now, we'll just allow the request
        # In a real implementation, you would track request counts per identifier
        
        return True, 0  # (allowed, remaining_requests)
    
    def backup_security_config(self) -> Dict:
        """Export security configuration for backup"""
        config = {
            'password_policy': {
                'min_length': self.password_min_length,
                'require_special': self.password_require_special,
                'require_numbers': self.password_require_numbers,
                'require_uppercase': self.password_require_uppercase
            },
            'session_policy': {
                'timeout_hours': self.session_timeout_hours
            },
            'lockout_policy': {
                'max_failed_attempts': self.max_failed_attempts,
                'lockout_duration_minutes': self.lockout_duration_minutes
            },
            'file_upload_policy': {
                'allowed_extensions': current_app.config.get('ALLOWED_EXTENSIONS', []),
                'max_size_mb': current_app.config.get('MAX_CONTENT_LENGTH', 0) / (1024 * 1024)
            }
        }
        
        return config
    
    def run_security_scan(self) -> Dict:
        """Run security scan and return results"""
        scan_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {},
            'overall_status': 'secure'
        }
        
        # Check for failed login attempts
        recent_failures = FailedLoginAttempt.query.filter(
            FailedLoginAttempt.attempt_time > datetime.utcnow() - timedelta(hours=24),
            FailedLoginAttempt.success == False
        ).count()
        
        scan_results['checks']['failed_login_attempts'] = {
            'count': recent_failures,
            'status': 'warning' if recent_failures > 50 else 'ok'
        }
        
        # Check user password security
        weak_passwords = 0
        users = User.query.all()
        for user in users:
            is_valid, errors = self.validate_password_strength(user.password)
            if not is_valid:
                weak_passwords += 1
        
        scan_results['checks']['weak_passwords'] = {
            'count': weak_passwords,
            'status': 'critical' if weak_passwords > 0 else 'ok'
        }
        
        # Check for any security issues
        critical_issues = [check for check in scan_results['checks'].values() 
                          if check['status'] == 'critical']
        warning_issues = [check for check in scan_results['checks'].values() 
                         if check['status'] == 'warning']
        
        if critical_issues:
            scan_results['overall_status'] = 'critical'
        elif warning_issues:
            scan_results['overall_status'] = 'warning'
        
        return scan_results
