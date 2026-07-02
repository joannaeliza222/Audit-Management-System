from flask import Blueprint, request, jsonify, session, g, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from typing import Dict

from app.services.chatgpt_ai import get_chatgpt_ai
from app.services.enhanced_chatbot_service import get_enhanced_chatbot_service
from app.services.claude_ai_service import get_claude_ai_service
from app.utils.embeddings import login_required
from flask_wtf.csrf import CSRFProtect, CSRFError

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Create blueprint
enhanced_chatbot_bp = Blueprint('enhanced_chatbot', __name__)

@enhanced_chatbot_bp.route('/chat', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def chat():
    """
    Enhanced chat endpoint with Claude AI integration and fallbacks
    Expects JSON: {"message": "user message", "state_name": "optional"}
    """
    
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        if len(message) > 1000:
            return jsonify({'error': 'Message too long (max 1000 characters)'}), 400
        
        state_name = data.get('state_name', session.get('state_name'))
        user_id = session.get('user_id')
        
        # Priority 1: Try Claude AI service (most capable)
        try:
            claude_service = get_claude_ai_service()
            claude_result = claude_service.process_message(message, user_id, state_name)
            if claude_result and not claude_result.get('error'):
                # Add debug info in development
                if current_app and current_app.config.get('DEBUG'):
                    claude_result['debug_info'] = {
                        'service': 'claude_ai',
                        'features': ['natural_language_processing', 'database_queries', 'security_sanitization']
                    }
                return jsonify(claude_result)
        except Exception as e:
            current_app.logger.warning(f"Claude AI service failed: {str(e)}")
        
        # Priority 2: Try direct database queries
        db_result = _handle_database_query_direct(message, user_id, state_name)
        if db_result and not db_result.get('error'):
            # Add debug info in development
            if current_app and current_app.config.get('DEBUG'):
                db_result['debug_info'] = {
                    'service': 'direct_database',
                    'features': ['pattern_matching', 'secure_queries']
                }
            return jsonify(db_result)
        
        # Priority 3: Fallback to original chatbot service
        try:
            ai_assistant = get_chatgpt_ai()
            result = ai_assistant.process_message(message, state_name, user_id)
            
            response_data = {
                'response': result['response'],
                'session_id': result['session_id'],
                'sources': result.get('sources', []),
                'intent_type': result.get('intent_type'),
                'confidence': result.get('confidence'),
                'query_type': result.get('query_type'),
                'timestamp': result.get('timestamp'),
                'suggestions': result.get('suggestions', [])
            }
            
            # Add debug info in development
            if current_app and current_app.config.get('DEBUG'):
                response_data['debug_info'] = {
                    'service': 'original_chatbot',
                    'features': ['semantic_search', 'faq_knowledge_base']
                }
            
            if result.get('error'):
                response_data['error'] = True
            
            return jsonify(response_data)
            
        except Exception as e:
            current_app.logger.warning(f"Original chatbot service failed: {str(e)}")
        
        # Final fallback: Generic error response
        return jsonify({
            'response': 'I apologize, but I\'m currently unable to process your request. Please try again later.',
            'query_type': 'error',
            'confidence': 0.0,
            'error': True,
            'debug_info': {
                'service': 'fallback_error',
                'message': 'All AI services unavailable'
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Chat endpoint error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


def _handle_database_query_direct(message: str, user_id: str, state_name: str) -> Dict:
    """
    Handle natural language database queries directly within Flask request context
    """
    try:
        from app import db
        from app.models import FAQ, User, DataDump, DraftFAQ
        from app.audit_models import AuditQuery, Commitment
        from sqlalchemy import func, and_, or_, desc
        
        # Get user role
        user_role = "viewer"
        if user_id:
            try:
                user = User.query.filter_by(id=user_id).first()
                user_role = user.role if user else "viewer"
            except Exception:
                pass
        
        message_lower = message.lower().strip()
        
        # Handle FAQ count queries
        if any(pattern in message_lower for pattern in ["how many faq", "number of faq", "total faq", "faq count"]):
            try:
                count = db.session.query(func.count(FAQ.id)).scalar()
                return {
                    'response': f"There are {count} FAQs in the system.",
                    'query_type': 'database_query',
                    'sources': ['FAQ table'],
                    'confidence': 0.9,
                    'session_id': session.get('session_id', 'temp'),
                    'intent_type': 'database_query'
                }
            except Exception as e:
                print(f"FAQ count error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Handle user count queries (admin only)
        if any(pattern in message_lower for pattern in ["how many user", "number of user", "total user", "user count"]):
            if user_role == 'admin':
                try:
                    count = db.session.query(func.count(User.id)).scalar()
                    return {
                        'response': f"There are {count} users in the system.",
                        'query_type': 'database_query',
                        'sources': ['User table'],
                        'confidence': 0.9,
                        'session_id': session.get('session_id', 'temp'),
                        'intent_type': 'database_query'
                    }
                except Exception as e:
                    print(f"User count error: {str(e)}")
                    return {'error': 'Database query failed'}
            else:
                return {
                    'response': "I don't have permission to access user information.",
                    'query_type': 'unauthorized',
                    'confidence': 0.8,
                    'session_id': session.get('session_id', 'temp'),
                    'intent_type': 'database_query'
                }
        
        # Handle data dump queries
        if any(pattern in message_lower for pattern in ["how many data dump", "number of data dump", "total data dump", "data dump count"]):
            try:
                count = db.session.query(func.count(DataDump.id)).scalar()
                return {
                    'response': f"There are {count} data dump requests in the system.",
                    'query_type': 'database_query',
                    'sources': ['DataDump table'],
                    'confidence': 0.9,
                    'session_id': session.get('session_id', 'temp'),
                    'intent_type': 'database_query'
                }
            except Exception as e:
                print(f"DataDump count error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Handle audit query counts
        if any(pattern in message_lower for pattern in ["how many audit", "number of audit", "total audit", "audit query count"]):
            try:
                count = db.session.query(func.count(AuditQuery.id)).scalar()
                return {
                    'response': f"There are {count} audit queries in the system.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.9,
                    'session_id': session.get('session_id', 'temp'),
                    'intent_type': 'database_query'
                }
            except Exception as e:
                print(f"AuditQuery count error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Handle pending audit queries
        if "pending audit" in message_lower:
            try:
                count = db.session.query(func.count(AuditQuery.id)).filter(
                    AuditQuery.status.in_(['received', 'in_progress', 'awaiting_response'])
                ).scalar()
                return {
                    'response': f"There are {count} pending audit queries in the system.",
                    'query_type': 'database_query',
                    'sources': ['AuditQuery table'],
                    'confidence': 0.9,
                    'session_id': session.get('session_id', 'temp'),
                    'intent_type': 'database_query'
                }
            except Exception as e:
                print(f"Pending audit query error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Enhanced state-specific queries
        if any(keyword in message_lower for keyword in ['from how many states', 'how many states', 'which states', 'states with', 'state wise', 'state-specific', 'by state', 'per state']):
            try:
                if 'from how many states' in message_lower or 'how many states' in message_lower:
                    # Count distinct states
                    from sqlalchemy import distinct
                    state_count = db.session.query(func.count(func.distinct(AuditQuery.state_name))).scalar()
                    return {
                        'response': f"Queries are coming from {state_count} different states across India.",
                        'query_type': 'database_query',
                        'sources': ['AuditQuery table'],
                        'confidence': 0.9,
                        'session_id': session.get('session_id', 'temp'),
                        'intent_type': 'state_query'
                    }
                else:
                    # Show top states by query volume
                    top_states = db.session.query(
                        AuditQuery.state_name,
                        func.count(AuditQuery.id).label('count')
                    ).group_by(AuditQuery.state_name).order_by(desc('count')).limit(5).all()
                    
                    if top_states:
                        states_list = [f"{state}: {count}" for state, count in top_states if state]
                        return {
                            'response': f"Top 5 states by query volume: {', '.join(states_list)}.",
                            'query_type': 'database_query',
                            'sources': ['AuditQuery table'],
                            'confidence': 0.9,
                            'session_id': session.get('session_id', 'temp'),
                            'intent_type': 'state_query'
                        }
            except Exception as e:
                print(f"State query error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Enhanced comparison queries
        if any(keyword in message_lower for keyword in ['compare states', 'which state has', 'top states', 'best state', 'worst state']):
            try:
                if 'which state has' in message_lower and ('most' in message_lower or 'highest' in message_lower):
                    # Find state with most queries
                    top_state = db.session.query(
                        AuditQuery.state_name,
                        func.count(AuditQuery.id).label('count')
                    ).group_by(AuditQuery.state_name).order_by(desc('count')).first()
                    
                    if top_state:
                        state, count = top_state
                        return {
                            'response': f"{state.title()} has the highest number of queries with {count} queries.",
                            'query_type': 'database_query',
                            'sources': ['AuditQuery table'],
                            'confidence': 0.9,
                            'session_id': session.get('session_id', 'temp'),
                            'intent_type': 'comparison_query'
                        }
                elif 'compare' in message_lower:
                    # General comparison info
                    state_stats = db.session.query(
                        AuditQuery.state_name,
                        func.count(AuditQuery.id).label('count')
                    ).group_by(AuditQuery.state_name).order_by(desc('count')).limit(3).all()
                    
                    if state_stats:
                        comparison = " | ".join([f"{state}: {count}" for state, count in state_stats if state])
                        return {
                            'response': f"State comparison: {comparison}",
                            'query_type': 'database_query',
                            'sources': ['AuditQuery table'],
                            'confidence': 0.9,
                            'session_id': session.get('session_id', 'temp'),
                            'intent_type': 'comparison_query'
                        }
            except Exception as e:
                print(f"Comparison query error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Enhanced trend queries
        if any(keyword in message_lower for keyword in ['trends', 'over time', 'monthly', 'daily', 'weekly', 'growth', 'increase', 'decrease', 'recent trends', 'activity patterns', 'engagement']):
            try:
                # Get recent activity (last 30 days)
                from datetime import datetime, timedelta
                thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                
                recent_count = db.session.query(func.count(AuditQuery.id)).filter(
                    AuditQuery.date_received >= thirty_days_ago.date()
                ).scalar()
                
                total_count = db.session.query(func.count(AuditQuery.id)).scalar()
                
                if total_count > 0:
                    percentage = (recent_count / total_count) * 100
                    trend_status = 'increasing' if percentage > 50 else 'stable'
                    return {
                        'response': f"In the last 30 days, there were {recent_count} queries ({percentage:.1f}% of total). Activity trends show {trend_status} engagement.",
                        'query_type': 'database_query',
                        'sources': ['AuditQuery table'],
                        'confidence': 0.9,
                        'session_id': session.get('session_id', 'temp'),
                        'intent_type': 'trend_query'
                    }
            except Exception as e:
                print(f"Trend query error: {str(e)}")
                return {'error': 'Database query failed'}
        
        # Complex natural language patterns
        if any(keyword in message_lower for keyword in ['state-wise distribution', 'activity patterns', 'engagement trending', 'tell me about']):
            if 'state' in message_lower:
                try:
                    # Provide state-wise overview
                    from sqlalchemy import distinct
                    state_count = db.session.query(func.count(func.distinct(AuditQuery.state_name))).scalar()
                    top_state = db.session.query(
                        AuditQuery.state_name,
                        func.count(AuditQuery.id).label('count')
                    ).group_by(AuditQuery.state_name).order_by(desc('count')).first()
                    
                    if top_state:
                        state, count = top_state
                        return {
                            'response': f"The system serves {state_count} states, with {state.title()} being the most active with {count} queries. State-wise distribution shows good geographic coverage.",
                            'query_type': 'database_query',
                            'sources': ['AuditQuery table'],
                            'confidence': 0.9,
                            'session_id': session.get('session_id', 'temp'),
                            'intent_type': 'state_query'
                        }
                except Exception as e:
                    print(f"Complex state query error: {str(e)}")
                    return {'error': 'Database query failed'}
        
        # Original state-specific queries (keep for backward compatibility)
        import re
        state_match = re.search(r'(?:from|in)\s+([A-Za-z\s]+)(?:\s+state|\s*$)', message_lower)
        if state_match:
            state_name_extracted = state_match.group(1).strip().title()
            
            if "faq" in message_lower and "how many" in message_lower:
                try:
                    count = db.session.query(func.count(FAQ.id)).filter(
                        FAQ.state_name == state_name_extracted
                    ).scalar()
                    return {
                        'response': f"There are {count} FAQs from {state_name_extracted}.",
                        'query_type': 'database_query',
                        'sources': ['FAQ table'],
                        'confidence': 0.9,
                        'session_id': session.get('session_id', 'temp'),
                        'intent_type': 'database_query'
                    }
                except Exception as e:
                    import logging
                    logging.error(f"State FAQ count error: {str(e)}")
                    return {'error': 'Database query failed'}
        
        return None  # No matching database query pattern
        
    except Exception as e:
        import logging
        logging.error(f"Direct database query error: {str(e)}")
        return {'error': 'Database query failed'}

@enhanced_chatbot_bp.route('/chat/clear', methods=['POST'])
@login_required
def clear_conversation():
    """Clear the current conversation history"""
    
    try:
        ai_assistant = get_chatgpt_ai()
        result = ai_assistant.conversation_memory.get_session_history()
        # Clear conversation history
        try:
            session.pop('chat_history', None)
            session.pop('chat_session_id', None)
        except Exception:
            pass
        return jsonify({'message': 'Conversation cleared successfully'})
    except Exception as e:
        return jsonify({'error': 'Failed to clear conversation'}), 500

@enhanced_chatbot_bp.route('/chat/stats', methods=['GET'])
@login_required
def conversation_stats():
    """Get statistics about the current conversation"""
    try:
        ai_assistant = get_chatgpt_ai()
        stats = ai_assistant.get_conversation_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': 'Failed to get conversation stats'}), 500

@enhanced_chatbot_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for the chatbot service"""
    try:
        ai_assistant = get_chatgpt_ai()
        memory_usage = ai_assistant.check_memory_usage()
        
        return jsonify({
            'status': 'healthy',
            'memory_usage_mb': memory_usage['rss_mb'],
            'cache_size': len(ai_assistant.conversation_memory.get_session_history()),
            'service': 'chatgpt_ai_assistant'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@enhanced_chatbot_bp.route('/suggestions', methods=['POST'])
@login_required
def get_suggestions():
    """Get contextual suggestions based on conversation"""
    
    try:
        data = request.get_json()
        if not data or 'partial' not in data:
            return jsonify({'error': 'Partial text is required'}), 400
        
        partial = data['partial'].strip()
        if len(partial) < 3:
            return jsonify({'suggestions': []})
        
        state_name = data.get('state_name', session.get('state_name'))
        
        # Get ChatGPT AI assistant
        ai_assistant = get_chatgpt_ai()
        suggestions = ai_assistant._generate_contextual_suggestions(partial, state_name)
        
        return jsonify({'suggestions': suggestions})
        
    except Exception as e:
        return jsonify({'error': 'Failed to get suggestions'}), 500

@enhanced_chatbot_bp.route('/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """
    Submit feedback for chatbot responses
    Expects JSON: {"session_id": "uuid", "message": "user message", "response": "bot response", "rating": 1-5}
    """
    
    try:
        data = request.get_json()
        required_fields = ['session_id', 'message', 'response', 'rating']
        
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        rating = data['rating']
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        # Here you would typically store feedback in a database
        # For now, we'll just log it
        user_id = session.get('user_id')
        current_app.logger.info(f"Chatbot feedback - User: {user_id}, Rating: {rating}, Session: {data['session_id']}")
        
        return jsonify({'message': 'Feedback submitted successfully'})
        
    except Exception as e:
        return jsonify({'error': 'Failed to submit feedback'}), 500
