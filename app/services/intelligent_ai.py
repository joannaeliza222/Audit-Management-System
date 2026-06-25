import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np
from flask import current_app, session
from sqlalchemy import func, and_, or_, text, desc
import psutil
import gc
import re

from app import db
from app.models import FAQ, User, Logs, DataDump, State
from app.utils.embeddings import get_bert_embeddings, normalize, find_related_questions_scored


class IntelligentAIAssistant:
    """Enhanced AI Assistant with application guidance and SQL-like query capabilities"""
    
    def __init__(self):
        self.conversation_memory = ConversationMemory()
        self.app_knowledge = self._load_app_knowledge()
        
    def _load_app_knowledge(self) -> Dict:
        """Load application knowledge base"""
        return {
            "features": {
                "audit_management": {
                    "description": "Manage audit processes and workflows",
                    "how_to": [
                        "Navigate to the dashboard to view ongoing audits",
                        "Use the audit creation form to start new audits",
                        "Track audit progress in real-time",
                        "Generate audit reports from the reports section"
                    ]
                },
                "datadump_requests": {
                    "description": "Request and manage data dumps",
                    "how_to": [
                        "Go to Data Dump section",
                        "Select your state and required data",
                        "Submit request for approval",
                        "Download approved data dumps",
                        "Upload completed documents"
                    ]
                },
                "user_management": {
                    "description": "Manage user accounts and permissions",
                    "how_to": [
                        "Admin can approve pending user registrations",
                        "Users can reset passwords via email",
                        "Role-based access control for different user types"
                    ]
                },
                "faq_management": {
                    "description": "Manage frequently asked questions",
                    "how_to": [
                        "Browse existing FAQs by category",
                        "Search for specific questions",
                        "Admin can add new FAQ entries",
                        "Filter FAQs by state or category"
                    ]
                }
            },
            "navigation": {
                "dashboard": "Main landing page showing overview and statistics",
                "datadump": "Request and manage data dumps",
                "pending": "View pending questions and approvals",
                "replied": "Manage FAQ database",
                "enhanced-chatbot": "AI assistant for help and queries"
            },
            "data_queries": {
                "user_stats": "Get statistics about users, registrations, roles",
                "datadump_stats": "Information about data dump requests and status",
                "audit_stats": "Audit progress and completion statistics",
                "state_stats": "State-specific data and metrics"
            }
        }
    
    def process_message(self, message: str, state_name: str = None, user_id: int = None) -> Dict:
        """Process user message with intelligent routing"""
        
        # Determine message type and route accordingly
        message_type = self._classify_message(message)
        
        if message_type == "app_guidance":
            response = self._handle_app_guidance(message)
        elif message_type == "data_query":
            response = self._handle_data_query(message, state_name, user_id)
        elif message_type == "general_help":
            response = self._handle_general_help(message)
        else:
            # Fall back to FAQ search
            response = self._handle_faq_search(message, state_name)
        
        # Add conversation memory
        session_id = self.conversation_memory.get_session_id()
        self.conversation_memory.add_turn(message, response['response'])
        
        return {
            'response': response['response'],
            'session_id': session_id,
            'sources': response.get('sources', []),
            'query_type': message_type,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _classify_message(self, message: str) -> str:
        """Classify the type of user message"""
        message_lower = message.lower()
        
        # Application guidance keywords
        guidance_keywords = [
            'how to', 'how do i', 'navigate', 'use', 'access', 'find', 
            'where is', 'how can', 'feature', 'functionality', 'dashboard'
        ]
        
        # Data query keywords
        data_keywords = [
            'how many', 'count', 'total', 'list', 'show me', 'statistics',
            'data', 'users', 'requests', 'dumps', 'states', 'audit',
            'number of', 'what is the', 'tell me about'
        ]
        
        # General help keywords
        help_keywords = [
            'help', 'assist', 'guide', 'support', 'hello', 'hi', 'what can'
        ]
        
        # Check message type
        if any(keyword in message_lower for keyword in guidance_keywords):
            return "app_guidance"
        elif any(keyword in message_lower for keyword in data_keywords):
            return "data_query"
        elif any(keyword in message_lower for keyword in help_keywords):
            return "general_help"
        else:
            return "faq_search"
    
    def _handle_app_guidance(self, message: str) -> Dict:
        """Handle application guidance questions"""
        message_lower = message.lower()
        
        # Check for specific features
        for feature_name, feature_info in self.app_knowledge["features"].items():
            if feature_name.replace('_', ' ') in message_lower or any(keyword in message_lower for keyword in [feature_name, feature_info["description"].lower()]):
                response = f"**{feature_name.replace('_', ' ').title()}**\n\n"
                response += f"{feature_info['description']}\n\n"
                response += "**How to use:**\n"
                for i, step in enumerate(feature_info["how_to"], 1):
                    response += f"{i}. {step}\n"
                
                return {
                    'response': response,
                    'sources': ['application_knowledge']
                }
        
        # Check for navigation help
        for nav_item, description in self.app_knowledge["navigation"].items():
            if nav_item in message_lower:
                return {
                    'response': f"**{nav_item.title()}**: {description}\n\nYou can access this from the main menu.",
                    'sources': ['application_knowledge']
                }
        
        # General guidance
        return {
            'response': self._generate_guidance_response(message),
            'sources': ['application_knowledge']
        }
    
    def _handle_data_query(self, message: str, state_name: str = None, user_id: int = None) -> Dict:
        """Handle SQL-like data queries"""
        try:
            # Parse the query
            query_result = self._execute_natural_language_query(message, state_name, user_id)
            
            if query_result:
                return {
                    'response': query_result['response'],
                    'sources': query_result.get('sources', ['database']),
                    'data': query_result.get('data')
                }
            else:
                return {
                    'response': "I couldn't understand that data query. Could you rephrase it? For example: 'How many users are registered?' or 'Show me data dump requests for Maharashtra'",
                    'sources': []
                }
        except Exception as e:
            current_app.logger.error(f"Data query error: {e}")
            return {
                'response': "I had trouble processing that data query. Please try rephrasing your question.",
                'sources': []
            }
    
    def _execute_natural_language_query(self, message: str, state_name: str = None, user_id: int = None) -> Optional[Dict]:
        """Execute natural language SQL-like queries"""
        message_lower = message.lower()
        
        # User statistics queries
        if 'user' in message_lower and ('how many' in message_lower or 'count' in message_lower or 'total' in message_lower):
            try:
                if 'admin' in message_lower:
                    count = User.query.filter_by(role='admin').count()
                    return {
                        'response': f"There are **{count} admin users** in the system.",
                        'data': {'admin_count': count}
                    }
                elif 'pending' in message_lower:
                    count = User.query.filter_by(is_approved=False).count()
                    return {
                        'response': f"There are **{count} users** pending approval.",
                        'data': {'pending_users': count}
                    }
                else:
                    total_users = User.query.count()
                    approved_users = User.query.filter_by(is_approved=True).count()
                    return {
                        'response': f"There are **{total_users} total users** in the system, with **{approved_users} approved** and **{total_users - approved_users} pending** approval.",
                        'data': {'total_users': total_users, 'approved_users': approved_users}
                    }
            except Exception as e:
                current_app.logger.error(f"User query error: {e}")
        
        # Data dump queries
        elif 'datadump' in message_lower or 'data dump' in message_lower or 'dump' in message_lower:
            try:
                if 'how many' in message_lower or 'count' in message_lower or 'total' in message_lower:
                    if 'pending' in message_lower:
                        count = DataDump.query.filter_by(status='PENDING').count()
                        return {
                            'response': f"There are **{count} pending data dump requests**.",
                            'data': {'pending_dumps': count}
                        }
                    elif 'approved' in message_lower:
                        count = DataDump.query.filter_by(status='APPROVED').count()
                        return {
                            'response': f"There are **{count} approved data dump requests**.",
                            'data': {'approved_dumps': count}
                        }
                    elif state_name:
                        count = DataDump.query.filter(DataDump.state_name.ilike(f'%{state_name}%')).count()
                        return {
                            'response': f"There are **{count} data dump requests** for {state_name}.",
                            'data': {'state_dumps': count}
                        }
                    else:
                        total_dumps = DataDump.query.count()
                        return {
                            'response': f"There are **{total_dumps} total data dump requests** in the system.",
                            'data': {'total_dumps': total_dumps}
                        }
                
                # State-specific data dump queries
                if state_name or any(state.lower() in message_lower for state in self._get_all_states()):
                    if not state_name:
                        # Try to extract state name from message
                        states = self._get_all_states()
                        for state in states:
                            if state.lower() in message_lower:
                                state_name = state
                                break
                    
                    if state_name:
                        dumps = DataDump.query.filter(DataDump.state_name.ilike(f'%{state_name}%')).all()
                        status_summary = {}
                        for dump in dumps:
                            status = dump.status
                            status_summary[status] = status_summary.get(status, 0) + 1
                        
                        response = f"**Data Dump Summary for {state_name}:**\n"
                        for status, count in status_summary.items():
                            response += f"- {status}: {count}\n"
                        
                        return {
                            'response': response,
                            'data': {'state_summary': status_summary}
                        }
                        
            except Exception as e:
                current_app.logger.error(f"Data dump query error: {e}")
        
        # State queries
        elif 'state' in message_lower and ('how many' in message_lower or 'list' in message_lower):
            try:
                states = self._get_all_states()
                if 'list' in message_lower:
                    response = "**Available States:**\n"
                    for i, state in enumerate(states[:10], 1):  # Limit to first 10
                        response += f"{i}. {state}\n"
                    if len(states) > 10:
                        response += f"... and {len(states) - 10} more states."
                    
                    return {
                        'response': response,
                        'data': {'states': states[:10]}
                    }
                else:
                    return {
                        'response': f"There are **{len(states)} states** configured in the system.",
                        'data': {'total_states': len(states)}
                    }
            except Exception as e:
                current_app.logger.error(f"State query error: {e}")
        
        # FAQ queries
        elif 'faq' in message_lower or 'question' in message_lower:
            try:
                total_faqs = FAQ.query.count()
                if state_name:
                    state_faqs = FAQ.query.filter(FAQ.state_name.ilike(f'%{state_name}%')).count()
                    return {
                        'response': f"There are **{state_faqs} FAQs** for {state_name} out of **{total_faqs} total FAQs** in the system.",
                        'data': {'state_faqs': state_faqs, 'total_faqs': total_faqs}
                    }
                else:
                    return {
                        'response': f"There are **{total_faqs} total FAQs** in the system.",
                        'data': {'total_faqs': total_faqs}
                    }
            except Exception as e:
                current_app.logger.error(f"FAQ query error: {e}")
        
        return None
    
    def _get_all_states(self) -> List[str]:
        """Get list of all states from DataDump"""
        try:
            states = db.session.query(DataDump.state_name).distinct().all()
            return [state[0] for state in states if state[0]]
        except Exception:
            return []
    
    def _handle_general_help(self, message: str) -> Dict:
        """Handle general help requests"""
        help_response = """🤖 **AI Assistant Help**

I can help you with:

**📊 Data Queries:**
- "How many users are registered?"
- "Show me data dump requests for Maharashtra"
- "What's the status of pending requests?"
- "Count total FAQs in the system"

**🔧 Application Guidance:**
- "How do I request a data dump?"
- "Where can I find audit reports?"
- "How to approve user registrations?"
- "Navigate to the dashboard"

**❓ General Questions:**
- Any questions about audit processes
- System functionality questions
- Help with features and navigation

**💡 Tips:**
- Ask questions in natural language
- Be specific about states or data you need
- I can understand SQL-like questions without table names

What would you like help with?"""
        
        return {
            'response': help_response,
            'sources': ['help_system']
        }
    
    def _handle_faq_search(self, message: str, state_name: str = None) -> Dict:
        """Handle FAQ search with enhanced results"""
        try:
            # Search in FAQ database
            results = find_related_questions_scored(
                question=message,
                reply="",
                memo_id=None,
                state_name=state_name
            )
            
            if results and len(results) > 0:
                # Format the best result
                best_result = results[0]
                response = f"**From FAQ:**\n\n"
                response += f"**Q:** {best_result.get('question', 'N/A')}\n\n"
                response += f"**A:** {best_result.get('reply', 'No answer available')}"
                
                # Add confidence score if available
                if 'score' in best_result:
                    confidence = best_result['score'] * 100
                    response += f"\n\n*Confidence: {confidence:.1f}%*"
                
                return {
                    'response': response,
                    'sources': ['faq_database'],
                    'faq_results': results[:3]  # Include top 3 results
                }
            else:
                # No FAQ found, provide helpful suggestions
                return {
                    'response': "I couldn't find specific information about that in our FAQ database. \n\n**Try asking about:**\n- Data dump requests and status\n- User management and approvals\n- Audit processes\n- System navigation and features\n\nOr ask me to show you statistics like 'How many users are registered?'",
                    'sources': []
                }
        except Exception as e:
            current_app.logger.error(f"FAQ search error: {e}")
            return {
                'response': "I had trouble searching the FAQ database. Please try rephrasing your question.",
                'sources': []
            }
    
    def _generate_guidance_response(self, message: str) -> str:
        """Generate contextual guidance response"""
        message_lower = message.lower()
        
        if 'dashboard' in message_lower:
            return """**Dashboard Navigation:**

The dashboard is your main landing page showing:
- Overview statistics
- Recent activity
- Quick actions
- System status

**Access:** Click "Dashboard" from the main menu."""
        
        elif 'upload' in message_lower or 'download' in message_lower:
            return """**File Upload/Download:**

**To Upload:**
1. Navigate to the relevant section (Data Dump, etc.)
2. Click "Upload" or "Choose File"
3. Select your file and confirm

**To Download:**
1. Find the item you want to download
2. Click the download icon/button
3. Save the file to your device"""
        
        elif 'profile' in message_lower or 'account' in message_lower:
            return """**Account Management:**

**Your Profile:**
- View and edit personal information
- Change password
- Check your role and permissions

**Access:** Look for your name/profile picture in the top right corner."""
        
        else:
            return """**I can help you navigate the Audit Management System!**

**Common Tasks:**
- Request data dumps
- View audit reports  
- Manage user approvals
- Browse FAQs
- Check system statistics

**Navigation:** Use the main menu to access different sections.

**Specific Help:** Ask me "How do I..." followed by what you want to do!"""
    
    def _generate_contextual_suggestions(self, partial: str, state_name: str = None) -> List[Dict]:
        """Generate contextual suggestions based on partial input"""
        suggestions = []
        
        partial_lower = partial.lower()
        
        # Data query suggestions
        if any(word in partial_lower for word in ['how many', 'count', 'total', 'number']):
            suggestions.extend([
                {'question': 'How many users are registered?', 'type': 'data_query'},
                {'question': 'How many data dump requests are pending?', 'type': 'data_query'},
                {'question': 'Total number of states in system?', 'type': 'data_query'},
                {'question': 'Count of approved data dumps?', 'type': 'data_query'}
            ])
        
        # Application guidance suggestions
        elif any(word in partial_lower for word in ['how to', 'how do', 'where', 'navigate']):
            suggestions.extend([
                {'question': 'How to request a data dump?', 'type': 'app_guidance'},
                {'question': 'Where can I find audit reports?', 'type': 'app_guidance'},
                {'question': 'How to approve user registrations?', 'type': 'app_guidance'},
                {'question': 'Navigate to dashboard?', 'type': 'app_guidance'}
            ])
        
        # State-specific suggestions
        elif 'state' in partial_lower:
            states = self._get_all_states()[:5]  # Top 5 states
            for state in states:
                suggestions.append({
                    'question': f'Data dump requests for {state}?',
                    'type': 'data_query'
                })
        
        # General help suggestions
        elif any(word in partial_lower for word in ['help', 'assist', 'guide']):
            suggestions.extend([
                {'question': 'Help with data dump requests', 'type': 'general_help'},
                {'question': 'Guide to user management', 'type': 'general_help'},
                {'question': 'Audit process assistance', 'type': 'general_help'}
            ])
        
        return suggestions[:5]  # Return top 5 suggestions
    
    def check_memory_usage(self) -> Dict:
        """Check memory usage of the AI assistant"""
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024
        }
    
    def get_conversation_stats(self) -> Dict:
        """Get conversation statistics"""
        return {
            'session_id': self.conversation_memory.get_session_id(),
            'turns': len(self.conversation_memory.get_session_history())
        }


class ConversationMemory:
    """Lightweight conversation memory manager"""
    
    def __init__(self, max_turns: int = 10, max_context_length: int = 2000):
        self.max_turns = max_turns
        self.max_context_length = max_context_length
        
    def get_session_id(self) -> str:
        """Get or create session ID for conversation tracking"""
        try:
            if 'chat_session_id' not in session:
                session['chat_session_id'] = str(uuid.uuid4())
            return session['chat_session_id']
        except RuntimeError:
            # Outside request context - use temporary session
            if not hasattr(self, '_temp_session_id'):
                self._temp_session_id = str(uuid.uuid4())
            return self._temp_session_id
    
    def add_turn(self, user_message: str, bot_response: str, context_data: Dict = None):
        """Add conversation turn to memory"""
        session_id = self.get_session_id()
        
        try:
            # Store in session for simplicity (can be moved to Redis later)
            if 'chat_history' not in session:
                session['chat_history'] = []
                
            turn = {
                'timestamp': datetime.utcnow().isoformat(),
                'user_message': user_message[:500],  # Limit message size
                'bot_response': bot_response[:1000],
                'context_data': context_data or {}
            }
            
            session['chat_history'].append(turn)
            
            # Limit history size
            if len(session['chat_history']) > self.max_turns:
                session['chat_history'] = session['chat_history'][-self.max_turns:]
                
        except RuntimeError:
            # Outside request context - skip storage
            pass
    
    def get_session_history(self) -> List[Dict]:
        """Get conversation history for current session"""
        try:
            return session.get('chat_history', [])
        except RuntimeError:
            return []


# Global instance
_intelligent_ai_instance = None

def get_intelligent_ai():
    """Get or create intelligent AI instance"""
    global _intelligent_ai_instance
    if _intelligent_ai_instance is None:
        _intelligent_ai_instance = IntelligentAIAssistant()
    return _intelligent_ai_instance
