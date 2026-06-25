import re
import json
import hashlib
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class DocumentSecurityService:
    """Security service for document injection detection and sanitization"""
    
    # Instruction trigger patterns
    INSTRUCTION_PATTERNS = [
        r'ignore\s+(all|previous|above|prior)\s+instructions\?',
        r'you\s+are\s+now',
        r'act\s+as',
        r'pretend\s+you\s+are',
        r'your\s+new\s+role',
        r'^\s*(system|assistant|user)\s*:',  # At start of line
        r'disregard.*instructions',
        r'forget.*instructions',
        r'override.*instructions'
    ]
    
    # Exfiltration trigger patterns
    EXFILTRATION_PATTERNS = [
        r'repeat\s+(everything|all|the\s+above|your\s+context|your\s+prompt)',
        r'output\s+(the|your)\s+(system\s+prompt|instructions|documents|context)',
        r'what\s+(is|are)\s+(your|the)\s+(instructions|system\s+prompt|other\s+documents)'
    ]
    
    # System prompt leakage patterns (first 20 tokens of each rule)
    SYSTEM_PROMPT_PATTERNS = [
        r'You are a document assistant',
        r'Your only job is to answer',
        'STRICT RULES.*never violate',
        r'Treat everything inside.*as raw data',
        r'Never reveal.*repeat.*summarise',
        r'Never output raw document text',
        r'If the answer cannot be found',
        r'If any text inside.*instructs you',
        r'document contained restricted content'
    ]
    
    def __init__(self):
        """Initialize the security service"""
        self.instruction_regex = self._compile_patterns(self.INSTRUCTION_PATTERNS)
        self.exfiltration_regex = self._compile_patterns(self.EXFILTRATION_PATTERNS)
        self.system_prompt_regex = self._compile_patterns(self.SYSTEM_PROMPT_PATTERNS)
    
    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compile regex patterns with case-insensitive flag"""
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE | re.MULTILINE))
            except re.error as e:
                print(f"Warning: Invalid regex pattern '{pattern}': {e}")
        return compiled
    
    def detect_injection(self, text: str) -> Tuple[bool, List[str]]:
        """
        Detect injection patterns in text
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (has_injection, matched_patterns)
        """
        matched_patterns = []
        
        # Check instruction patterns
        for regex in self.instruction_regex:
            matches = regex.findall(text)
            if matches:
                matched_patterns.extend([f"instruction_{match}" for match in matches])
        
        # Check exfiltration patterns
        for regex in self.exfiltration_regex:
            matches = regex.findall(text)
            if matches:
                matched_patterns.extend([f"exfiltration_{match}" for match in matches])
        
        return len(matched_patterns) > 0, matched_patterns
    
    def sanitize_text(self, text: str, document_id: str, chunk_index: int) -> Tuple[str, bool, List[str]]:
        """
        Sanitize text by replacing injection patterns
        
        Args:
            text: Text to sanitize
            document_id: Document ID for logging
            chunk_index: Chunk index for logging
            
        Returns:
            Tuple of (sanitized_text, was_flagged, flagged_patterns)
        """
        sanitized_text = text
        flagged_patterns = []
        was_flagged = False
        
        # Check for injection patterns
        has_injection, matched_patterns = self.detect_injection(text)
        
        if has_injection:
            was_flagged = True
            flagged_patterns = matched_patterns
            
            # Replace each matched pattern
            for regex in self.instruction_regex + self.exfiltration_regex:
                sanitized_text = regex.sub('[CONTENT REMOVED - POLICY VIOLATION]', sanitized_text)
            
            # Log the sanitization event
            self._log_sanitization(document_id, chunk_index, matched_patterns)
        
        return sanitized_text, was_flagged, flagged_patterns
    
    def validate_query(self, question_text: str) -> Dict:
        """
        Validate user query for injection attempts
        
        Args:
            question_text: User's question text
            
        Returns:
            Dict with validation result
        """
        has_injection, matched_patterns = self.detect_injection(question_text)
        
        if has_injection:
            return {
                'valid': False,
                'reason': 'query_injection_attempt',
                'sanitised_query': None,
                'matched_patterns': matched_patterns
            }
        
        return {
            'valid': True,
            'sanitised_query': question_text,
            'matched_patterns': []
        }
    
    def validate_response(self, response_text: str, retrieved_document_ids: List[str]) -> Dict:
        """
        Validate Claude response for injection or data leakage
        
        Args:
            response_text: Claude's response text
            retrieved_document_ids: Document IDs used in retrieval
            
        Returns:
            Dict with validation result
        """
        issues = []
        
        # Check for system prompt leakage
        for regex in self.system_prompt_regex:
            if regex.search(response_text):
                issues.append('system_prompt_leakage')
        
        # Check for role markers at line start
        if re.search(r'^\s*(SYSTEM|ASSISTANT|USER)\s*:', response_text, re.MULTILINE):
            issues.append('role_markers_detected')
        
        # Check for hallucinated content (sentences without citations)
        sentences = re.split(r'[.!?]+', response_text)
        non_cited_sentences = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and not re.search(r'\(source:.*?\)|\[.*?\]', sentence, re.IGNORECASE):
                non_cited_sentences += 1
        
        if non_cited_sentences > 3:
            issues.append('excessive_uncited_content')
        
        # Check for document ID leakage (cross-user data leakage)
        for doc_id in retrieved_document_ids:
            if doc_id in response_text:
                issues.append('document_id_leakage')
        
        if issues:
            return {
                'valid': False,
                'issues': issues,
                'injection_detected': True
            }
        
        return {
            'valid': True,
            'injection_detected': False
        }
    
    def _log_sanitization(self, document_id: str, chunk_index: int, patterns: List[str]):
        """Log sanitization event (implementation depends on logging system)"""
        log_entry = {
            'documentId': document_id,
            'chunkIndex': chunk_index,
            'patterns': patterns,
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'content_sanitization'
        }
        
        # This would integrate with the audit logging system
        # For now, we'll just print a warning (in production, use proper logging)
        print(f"SECURITY: Content sanitized - {log_entry}")
    
    def generate_safe_filename(self, filename: str) -> str:
        """
        Generate a safe filename by removing potentially dangerous characters
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove path traversal attempts
        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        
        # Remove null bytes and other dangerous characters
        filename = filename.replace('\x00', '').replace('\r', '').replace('\n', '')
        
        # Limit length and remove dangerous extensions
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:250] + ('.' + ext if ext else '')
        
        return filename.strip()
    
    def validate_mime_type(self, filename: str, allowed_types: set) -> bool:
        """
        Validate MIME type against allowed types
        
        Args:
            filename: Filename to check
            allowed_types: Set of allowed MIME types
            
        Returns:
            True if MIME type is allowed
        """
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type in allowed_types if mime_type else False
    
    def scan_for_malicious_content(self, content: bytes) -> Dict:
        """
        Basic content scanning for malicious patterns
        
        Args:
            content: File content as bytes
            
        Returns:
            Dict with scan results
        """
        threats = []
        
        # Convert to string for pattern matching
        try:
            content_str = content.decode('utf-8', errors='ignore')
        except (UnicodeDecodeError, AttributeError):
            content_str = ""
        
        # Check for common malicious patterns
        malicious_patterns = [
            r'<script[^>]*>.*?</script>',  # Scripts
            r'javascript:',  # JavaScript URLs
            r'vbscript:',  # VBScript URLs
            r'on\w+\s*=',  # Event handlers
            r'eval\s*\(',  # eval() function
            r'document\.cookie',  # Cookie access
        ]
        
        for pattern in malicious_patterns:
            if re.search(pattern, content_str, re.IGNORECASE):
                threats.append(pattern)
        
        return {
            'clean': len(threats) == 0,
            'threats': threats,
            'scan_time': datetime.utcnow().isoformat()
        }


class InjectionDetector:
    """Legacy class for backward compatibility"""
    
    def __init__(self):
        self.security_service = DocumentSecurityService()
    
    def detect_and_sanitize(self, text: str, document_id: str, chunk_index: int) -> Tuple[str, bool]:
        """Detect and sanitize injection patterns"""
        sanitized, flagged, patterns = self.security_service.sanitize_text(text, document_id, chunk_index)
        return sanitized, flagged
    
    def validate_query(self, query: str) -> bool:
        """Validate query for injection attempts"""
        result = self.security_service.validate_query(query)
        return result['valid']
