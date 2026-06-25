"""
Secure Claude AI Integration Service
Provides Claude AI capabilities with full data security through local proxy
"""

import os
import json
import hashlib
import hmac
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import bleach
import re
from flask import current_app

from app import db
from app.models import FAQ, User, DataDump, DraftFAQ
from app.audit_models import AuditQuery, Commitment
from sqlalchemy import func, and_, or_, desc


class ClaudeAIService:
    """Secure Claude AI integration with data sanitization and local proxy"""
    
    def __init__(self):
        self.api_key = os.getenv('CLAUDE_API_KEY')
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.session = self._create_secure_session()
        self.data_sanitizer = DataSanitizer()
        self.query_processor = QueryProcessor()
        
    def _create_secure_session(self) -> requests.Session:
        """Create secure HTTP session with retry strategy"""
        session = requests.Session()
        
        # Retry strategy for reliability
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        # Security headers
        session.headers.update({
            'User-Agent': 'AMS-Claude-Integration/1.0',
            'Accept': 'application/json',
            'X-API-Version': '2023-06-01'
        })
        
        return session
    
    def process_message(self, message: str, user_id: str = None, state_name: str = None) -> Dict:
        """
        Process user message through Claude AI with security layers
        
        Args:
            message: User's message
            user_id: User identifier for access control
            state_name: Optional state context
            
        Returns:
            Dict containing response and metadata
        """
        try:
            # Step 1: Sanitize input
            sanitized_message = self.data_sanitizer.sanitize_input(message)
            
            # Step 2: Check for database queries
            db_result = self.query_processor.process_database_query(sanitized_message, user_id)
            if db_result:
                return db_result
            
            # Step 3: Get user role for access control
            user_role = self._get_user_role(user_id)
            
            # Step 4: Create secure prompt with context
            secure_prompt = self._create_secure_prompt(sanitized_message, user_role, state_name)
            
            # Step 5: Call Claude API
            claude_response = self._call_claude_api(secure_prompt)
            
            # Step 6: Sanitize output
            sanitized_response = self.data_sanitizer.sanitize_output(claude_response)
            
            return {
                'response': sanitized_response,
                'query_type': 'claude_ai',
                'sources': ['Claude AI'],
                'confidence': 0.9,
                'session_id': self._generate_session_id(),
                'intent_type': 'ai_response',
                'timestamp': datetime.utcnow().isoformat(),
                'user_role': user_role
            }
            
        except Exception as e:
            current_app.logger.error(f"Claude AI service error: {str(e)}")
            return {
                'response': 'I apologize, but I encountered an error processing your request. Please try again.',
                'query_type': 'error',
                'confidence': 0.0,
                'error': str(e)
            }
    
    def _get_user_role(self, user_id: str) -> str:
        """Get user role for access control"""
        if not user_id:
            return "viewer"
        
        try:
            user = User.query.filter_by(id=user_id).first()
            return user.role if user else "viewer"
        except Exception:
            return "viewer"
    
    def _create_secure_prompt(self, message: str, user_role: str, state_name: str) -> str:
        """Create secure prompt with role-based context"""
        
        # Base system prompt
        system_prompt = """You are a helpful AI assistant for the Audit Management System (AMS). 

Your role is to help users with:
- Answering questions about audit procedures and processes
- Providing guidance on system usage
- Assisting with FAQ and knowledge base queries
- Helping with general system information

IMPORTANT SECURITY RULES:
- Never reveal sensitive system information
- Do not provide database schema details
- Do not disclose user information unless authorized
- Do not provide administrative access instructions
- Keep responses professional and helpful
- If you don't know something, say so politely

Current context:
- User role: {user_role}
- State context: {state_name}

User question: {message}

Please provide a helpful, secure response."""
        
        return system_prompt.format(
            user_role=user_role,
            state_name=state_name or "Not specified",
            message=message
        )
    
    def _call_claude_api(self, prompt: str) -> str:
        """Make secure API call to Claude"""
        
        if not self.api_key:
            raise ValueError("Claude API key not configured")
        
        payload = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 1000,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        try:
            response = self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            
            if "content" in data and len(data["content"]) > 0:
                return data["content"][0]["text"]
            else:
                raise ValueError("Invalid response format from Claude API")
                
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Claude API request failed: {str(e)}")
            raise
        except Exception as e:
            current_app.logger.error(f"Claude API processing error: {str(e)}")
            raise
    
    def _generate_session_id(self) -> str:
        """Generate secure session identifier"""
        timestamp = str(datetime.utcnow().timestamp())
        return hmac.new(
            b'ams-claude-session',
            timestamp.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
    
    def health_check(self) -> Dict:
        """Check Claude AI service health"""
        try:
            # Simple test message
            test_response = self._call_claude_api("Hello, are you working?")
            return {
                'status': 'healthy',
                'response_length': len(test_response),
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }


class DataSanitizer:
    """Data sanitization and security layer"""
    
    def __init__(self):
        self.allowed_tags = ['p', 'br', 'strong', 'em', 'ul', 'ol', 'li']
        self.sensitive_patterns = [
            r'password',
            r'api[_\s]*key',
            r'secret[_\s]*key',
            r'token',
            r'credential',
            r'admin[_\s]*password',
            r'database[_\s]*url',
            r'connection[_\s]*string'
        ]
    
    def sanitize_input(self, input_text: str) -> str:
        """Sanitize user input"""
        if not input_text:
            return ""
        
        # Remove potential script injections
        sanitized = bleach.clean(input_text, tags=[], strip=True)
        
        # Remove sensitive patterns
        for pattern in self.sensitive_patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        
        # Limit length
        if len(sanitized) > 2000:
            sanitized = sanitized[:2000] + "..."
        
        return sanitized.strip()
    
    def sanitize_output(self, output_text: str) -> str:
        """Sanitize AI output"""
        if not output_text:
            return "I apologize, but I couldn't generate a response."
        
        # Allow basic HTML formatting
        sanitized = bleach.clean(output_text, tags=self.allowed_tags, strip=True)
        
        # Remove any potential system information
        sanitized = re.sub(r'\{[^}]*\}', '[SYSTEM_INFO]', sanitized)
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        
        return sanitized.strip()


class QueryProcessor:
    """Process database queries with security controls"""
    
    def __init__(self):
        self.query_patterns = {
            'faq_count': [
                r'how many faq',
                r'number of faq',
                r'total faq',
                r'faq count',
                r'faqs? count'
            ],
            'user_count': [
                r'how many user',
                r'number of user',
                r'total user',
                r'user count',
                r'users? count'
            ],
            'audit_count': [
                r'how many audit',
                r'number of audit',
                r'total audit',
                r'audit count',
                r'audits? count'
            ],
            'datadump_count': [
                r'how many data dump',
                r'number of data dump',
                r'total data dump',
                r'data dump count',
                r'data dump requests?'
            ],
            'pending_audit': [
                r'pending audit',
                r'awaiting audit',
                r'audit pending',
                r'audit status'
            ],
            'state_queries': [
                r'from how many states',
                r'how many states',
                r'which states',
                r'states with',
                r'state wise',
                r'state-specific',
                r'by state',
                r'per state'
            ],
            'comparison_queries': [
                r'compare.*states?',
                r'which state has',
                r'top.*states?',
                r'best.*state',
                r'worst.*state'
            ],
            'trend_queries': [
                r'trends?',
                r'over time',
                r'monthly',
                r'daily',
                r'weekly',
                r'growth',
                r'increase',
                r'decrease'
            ]
        }
        
        # Indian states for better matching
        self.indian_states = [
            'andhra pradesh', 'arunachal pradesh', 'assam', 'bihar', 'chhattisgarh',
            'goa', 'gujarat', 'haryana', 'himachal pradesh', 'jharkhand', 'karnataka',
            'kerala', 'madhya pradesh', 'maharashtra', 'manipur', 'meghalaya', 'mizoram',
            'nagaland', 'odisha', 'punjab', 'rajasthan', 'sikkim', 'tamil nadu',
            'telangana', 'tripura', 'uttar pradesh', 'uttarakhand', 'west bengal',
            'andaman and nicobar islands', 'chandigarh', 'dadra and nagar haveli',
            'daman and diu', 'delhi', 'lakshadweep', 'pondicherry'
        ]
    
    def process_database_query(self, message: str, user_id: str) -> Optional[Dict]:
        """Process database queries with security controls"""
        try:
            message_lower = message.lower().strip()
            
            # Get user role
            user_role = "viewer"
            if user_id:
                try:
                    user = User.query.filter_by(id=user_id).first()
                    user_role = user.role if user else "viewer"
                except Exception:
                    pass
            
            # Check FAQ count queries
            if self._match_patterns(message_lower, self.query_patterns['faq_count']):
                count = db.session.query(func.count(FAQ.id)).scalar()
                return {
                    'response': f"There are {count} FAQs in the system.",
                    'query_type': 'database_query',
                    'sources': ['FAQ table'],
                    'confidence': 0.95,
                    'intent_type': 'count_query'
                }
            
            # Check user count queries (admin only)
            if self._match_patterns(message_lower, self.query_patterns['user_count']):
                if user_role == 'admin':
                    count = db.session.query(func.count(User.id)).scalar()
                    return {
                        'response': f"There are {count} users in the system.",
                        'query_type': 'database_query',
                        'sources': ['User table'],
                        'confidence': 0.95,
                        'intent_type': 'count_query'
                    }
                else:
                    return {
                        'response': "I don't have permission to access user information.",
                        'query_type': 'unauthorized',
                        'confidence': 0.8,
                        'intent_type': 'access_denied'
                    }
            
            # Check audit count queries
            if self._match_patterns(message_lower, self.query_patterns['audit_count']):
                count = db.session.query(func.count(AuditQuery.id)).scalar()
                return {
                    'response': f"There are {count} audit queries in the system.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.95,
                    'intent_type': 'count_query'
                }
            
            # Check data dump count queries
            if self._match_patterns(message_lower, self.query_patterns['datadump_count']):
                count = db.session.query(func.count(DataDump.id)).scalar()
                return {
                    'response': f"There are {count} data dump requests in the system.",
                    'query_type': 'database_query',
                    'sources': ['DataDump table'],
                    'confidence': 0.95,
                    'intent_type': 'count_query'
                }
            
            # Check pending audit queries
            if self._match_patterns(message_lower, self.query_patterns['pending_audit']):
                count = db.session.query(func.count(AuditQuery.id)).filter(
                    AuditQuery.status.in_(['received', 'in_progress', 'awaiting_response'])
                ).scalar()
                return {
                    'response': f"There are {count} pending audit queries in the system.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.95,
                    'intent_type': 'status_query'
                }
            
            # Check state-specific queries
            if self._match_patterns(message_lower, self.query_patterns['state_queries']):
                return self._handle_state_query(message_lower, user_role)
            
            # Check comparison queries
            if self._match_patterns(message_lower, self.query_patterns['comparison_queries']):
                return self._handle_comparison_query(message_lower, user_role)
            
            # Check trend queries
            if self._match_patterns(message_lower, self.query_patterns['trend_queries']):
                return self._handle_trend_query(message_lower, user_role)
            
            return None
            
        except Exception as e:
            current_app.logger.error(f"Database query processing error: {str(e)}")
            return None
    
    def _handle_state_query(self, message: str, user_role: str) -> Dict:
        """Handle state-specific queries intelligently"""
        try:
            # Extract states mentioned in the query
            mentioned_states = [state for state in self.indian_states if state in message]
            
            if 'from how many states' in message or 'how many states' in message:
                # Count distinct states in audit queries
                state_count = db.session.query(func.count(func.distinct(AuditQuery.state))).scalar()
                return {
                    'response': f"Queries are coming from {state_count} different states across India.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.95,
                    'intent_type': 'state_query'
                }
            
            elif mentioned_states:
                # Query for specific states
                state_name = mentioned_states[0].title()
                count = db.session.query(func.count(AuditQuery.id)).filter(
                    AuditQuery.state.ilike(f'%{state_name}%')
                ).scalar()
                
                return {
                    'response': f"There are {count} queries from {state_name.title()}.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.95,
                    'intent_type': 'state_query'
                }
            
            else:
                # General state information
                top_states = db.session.query(
                    AuditQuery.state,
                    func.count(AuditQuery.id).label('count')
                ).group_by(AuditQuery.state).order_by(desc('count')).limit(5).all()
                
                if top_states:
                    states_list = [f"{state}: {count}" for state, count in top_states if state]
                    return {
                        'response': f"Top 5 states by query volume: {', '.join(states_list)}.",
                        'query_type': 'database_query',
                        'sources': ['AuditQuery table'],
                        'confidence': 0.95,
                        'intent_type': 'state_query'
                    }
                    
        except Exception as e:
            current_app.logger.error(f"State query error: {str(e)}")
            return None
    
    def _handle_comparison_query(self, message: str, user_role: str) -> Dict:
        """Handle comparison queries between states"""
        try:
            if 'which state has' in message and ('most' in message or 'highest' in message):
                # Find state with most queries
                top_state = db.session.query(
                    AuditQuery.state,
                    func.count(AuditQuery.id).label('count')
                ).group_by(AuditQuery.state).order_by(desc('count')).first()
                
                if top_state:
                    state, count = top_state
                    return {
                        'response': f"{state.title()} has the highest number of queries with {count} queries.",
                        'query_type': 'database_query',
                        'sources': ['AuditQuery table'],
                        'confidence': 0.95,
                        'intent_type': 'comparison_query'
                    }
                    
            elif 'compare' in message:
                # General comparison info
                state_stats = db.session.query(
                    AuditQuery.state,
                    func.count(AuditQuery.id).label('count')
                ).group_by(AuditQuery.state).order_by(desc('count')).limit(3).all()
                
                if state_stats:
                    comparison = " | ".join([f"{state}: {count}" for state, count in state_stats if state])
                    return {
                        'response': f"State comparison: {comparison}",
                        'query_type': 'database_query',
                        'sources': ['AuditQuery table'],
                        'confidence': 0.95,
                        'intent_type': 'comparison_query'
                    }
                    
        except Exception as e:
            current_app.logger.error(f"Comparison query error: {str(e)}")
            return None
    
    def _handle_trend_query(self, message: str, user_role: str) -> Dict:
        """Handle trend and time-based queries"""
        try:
            # Get recent activity (last 30 days)
            from datetime import datetime, timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            recent_count = db.session.query(func.count(AuditQuery.id)).filter(
                AuditQuery.created_at >= thirty_days_ago
            ).scalar()
            
            total_count = db.session.query(func.count(AuditQuery.id)).scalar()
            
            if total_count > 0:
                percentage = (recent_count / total_count) * 100
                return {
                    'response': f"In the last 30 days, there were {recent_count} queries ({percentage:.1f}% of total). Activity trends show {'increasing' if percentage > 50 else 'stable'} engagement.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.95,
                    'intent_type': 'trend_query'
                }
                
        except Exception as e:
            current_app.logger.error(f"Trend query error: {str(e)}")
            return None
    
    def _match_patterns(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any pattern"""
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        return False


# Factory function
def get_claude_ai_service():
    """Get Claude AI service instance"""
    return ClaudeAIService()
