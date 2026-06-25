import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np
from flask import current_app, session
from sqlalchemy import func, and_, or_
import psutil
import gc

from app import db
from app.models import FAQ, User, Logs
from app.utils.embeddings import get_bert_embeddings, normalize, find_related_questions_scored


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
            
            # Keep only recent turns to manage memory
            if len(session['chat_history']) > self.max_turns:
                session['chat_history'] = session['chat_history'][-self.max_turns:]
        except RuntimeError:
            # Outside request context - use in-memory storage
            if not hasattr(self, '_temp_history'):
                self._temp_history = []
            
            turn = {
                'timestamp': datetime.utcnow().isoformat(),
                'user_message': user_message[:500],
                'bot_response': bot_response[:1000],
                'context_data': context_data or {}
            }
            
            self._temp_history.append(turn)
            if len(self._temp_history) > self.max_turns:
                self._temp_history = self._temp_history[-self.max_turns:]
    
    def get_context(self) -> str:
        """Get formatted conversation context"""
        try:
            if 'chat_history' not in session:
                return ""
                
            context_parts = []
            total_length = 0
            
            # Add recent conversation history
            for turn in session['chat_history'][-5:]:  # Last 5 turns for context
                context_text = f"User: {turn['user_message']}\nAssistant: {turn['bot_response']}\n"
                if total_length + len(context_text) > self.max_context_length:
                    break
                context_parts.append(context_text)
                total_length += len(context_text)
            
            return "\n".join(context_parts)
        except RuntimeError:
            # Outside request context - use temporary history
            if not hasattr(self, '_temp_history'):
                return ""
            
            context_parts = []
            total_length = 0
            
            for turn in self._temp_history[-5:]:
                context_text = f"User: {turn['user_message']}\nAssistant: {turn['bot_response']}\n"
                if total_length + len(context_text) > self.max_context_length:
                    break
                context_parts.append(context_text)
                total_length += len(context_text)
            
            return "\n".join(context_parts)
    
    def clear(self):
        """Clear conversation memory"""
        try:
            session.pop('chat_history', None)
            session.pop('chat_session_id', None)
        except RuntimeError:
            # Outside request context - clear temporary storage
            if hasattr(self, '_temp_history'):
                self._temp_history = []
            if hasattr(self, '_temp_session_id'):
                delattr(self, '_temp_session_id')


class EnhancedAIChatbot:
    """Lightweight RAG-based chatbot optimized for 8GB RAM"""
    
    def __init__(self):
        self.memory = ConversationMemory()
        self.embedding_cache = {}
        self.max_cache_size = 1000
        
    def check_memory_usage(self) -> Dict:
        """Monitor memory usage for optimization"""
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024,
            'percent': process.memory_percent()
        }
    
    def optimize_memory(self):
        """Force garbage collection and cache cleanup"""
        gc.collect()
        
        # Clear embedding cache if it's too large
        if len(self.embedding_cache) > self.max_cache_size:
            # Keep only recent entries
            items = list(self.embedding_cache.items())
            self.embedding_cache = dict(items[-self.max_cache_size//2:])
    
    def retrieve_relevant_data(self, query: str, state_name: str = None, 
                             max_results: int = 5) -> List[Dict]:
        """Retrieve relevant FAQ data using vector search"""
        try:
            # Get embedding for query
            query_emb = normalize(get_bert_embeddings(query))
            if query_emb is None:
                return []
            
            # Search in FAQ database with proper context
            try:
                results = find_related_questions_scored(
                    question=query,
                    reply="",  # Search only by question
                    memo_id=None,
                    state_name=state_name
                )
            except RuntimeError:
                # Outside app context - create a simple mock response
                # This happens during testing or when called from outside request
                return []
            
            # Filter and limit results
            filtered_results = []
            for result in results[:max_results]:
                if result['similarity'] >= 0.7:  # High similarity threshold
                    filtered_results.append({
                        'question': result['question'],
                        'answer': result['reply'],
                        'similarity': result['similarity'],
                        'state': result['state_name'],
                        'memo_id': result['memo_id']
                    })
            
            return filtered_results
            
        except Exception as e:
            current_app.logger.error(f"Error retrieving relevant data: {e}")
            return []
    
    def generate_contextual_response(self, query: str, relevant_data: List[Dict]) -> str:
        """Generate response based on retrieved data and conversation context"""
        
        # Get conversation context
        conversation_context = self.memory.get_context()
        
        # Build context prompt
        context_parts = []
        
        if conversation_context:
            context_parts.append("Recent Conversation:")
            context_parts.append(conversation_context)
            context_parts.append("")
        
        if relevant_data:
            context_parts.append("Relevant Information from Database:")
            for i, data in enumerate(relevant_data, 1):
                context_parts.append(f"{i}. Q: {data['question']}")
                context_parts.append(f"   A: {data['answer']}")
                context_parts.append(f"   (Similarity: {data['similarity']:.2f})")
            context_parts.append("")
        
        # Create response based on available data
        if not relevant_data:
            response = self._generate_fallback_response(query)
        else:
            # Use the most relevant answer
            best_match = relevant_data[0]
            if best_match['similarity'] > 0.9:
                # Very high similarity - use direct answer
                response = best_match['answer']
            else:
                # Moderate similarity - adapt the answer
                response = self._adapt_answer(query, best_match, relevant_data[1:])
        
        return response
    
    def _adapt_answer(self, query: str, best_match: Dict, other_matches: List[Dict]) -> str:
        """Adapt the best matching answer to the current query"""
        
        # Simple adaptation - can be enhanced with more sophisticated logic
        base_answer = best_match['answer']
        
        # If the query is very similar to the stored question, return as-is
        if best_match['similarity'] > 0.85:
            return base_answer
        
        # Otherwise, add a contextual prefix
        adapted_response = f"Based on similar questions, here's what I found:\n\n{base_answer}"
        
        # Add additional context if available
        if other_matches and len(other_matches) > 0:
            adapted_response += "\n\nYou might also find this related information helpful."
        
        return adapted_response
    
    def _generate_fallback_response(self, query: str) -> str:
        """Generate helpful fallback response when no relevant data is found"""
        
        fallback_responses = [
            "I don't have specific information about that in my database. Could you try rephrasing your question or provide more details?",
            "I couldn't find relevant information for your query. You might want to check with your system administrator for this specific topic.",
            "That's an interesting question, but I don't have the specific information you're looking for. Is there anything else I can help you with?",
            "I'm not finding relevant data for your question. Try searching with different keywords or check the FAQ section manually."
        ]
        
        # Simple selection based on query characteristics
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['how to', 'how do', 'procedure', 'process']):
            return "I don't have the specific procedure information you're looking for. Please consult your system administrator or user manual for detailed instructions."
        
        if any(word in query_lower for word in ['error', 'problem', 'issue', 'bug']):
            return "I don't have information about this specific issue. Please report this to your technical support team with details about the error you're experiencing."
        
        if any(word in query_lower for word in ['what is', 'define', 'explain']):
            return "I don't have a definition for that term in my current database. Please check the documentation or ask your administrator for clarification."
        
        # Return a generic fallback
        import random
        return random.choice(fallback_responses)
    
    def process_message(self, message: str, state_name: str = None, 
                       user_id: int = None) -> Dict:
        """Process user message and generate response"""
        
        try:
            # Check memory usage
            memory_usage = self.check_memory_usage()
            if memory_usage['rss_mb'] > 600:  # If using more than 600MB
                self.optimize_memory()
            
            # Log the query
            if user_id:
                user = User.query.get(user_id)
                if user:
                    log_entry = Logs(action=f"AI Query: {message[:100]}", 
                                     user_email=user.email)
                    db.session.add(log_entry)
                    db.session.commit()
            
            # Retrieve relevant data
            relevant_data = self.retrieve_relevant_data(message, state_name)
            
            # Generate response
            response = self.generate_contextual_response(message, relevant_data)
            
            # Store in conversation memory
            self.memory.add_turn(message, response, {
                'relevant_count': len(relevant_data),
                'state_name': state_name
            })
            
            return {
                'response': response,
                'sources': relevant_data,
                'session_id': self.memory.get_session_id(),
                'memory_usage': memory_usage
            }
            
        except Exception as e:
            try:
                current_app.logger.error(f"Error processing message: {e}")
            except RuntimeError:
                # Outside request context - use print for debugging
                print(f"Error processing message: {e}")
            
            error_response = "I'm experiencing technical difficulties. Please try again later."
            
            # Still log the attempt
            self.memory.add_turn(message, error_response, {'error': str(e)})
            
            return {
                'response': error_response,
                'sources': [],
                'session_id': self.memory.get_session_id(),
                'error': True
            }
    
    def clear_conversation(self):
        """Clear current conversation"""
        self.memory.clear()
        return {'message': 'Conversation cleared'}
    
    def get_conversation_stats(self) -> Dict:
        """Get statistics about current conversation"""
        history = session.get('chat_history', [])
        return {
            'session_id': self.memory.get_session_id(),
            'turns': len(history),
            'duration': None if not history else (
                datetime.utcnow() - datetime.fromisoformat(history[0]['timestamp'])
            ).total_seconds()
        }


# Global chatbot instance
_chatbot_instance = None

def get_chatbot() -> EnhancedAIChatbot:
    """Get or create chatbot instance"""
    global _chatbot_instance
    if _chatbot_instance is None:
        _chatbot_instance = EnhancedAIChatbot()
    return _chatbot_instance
