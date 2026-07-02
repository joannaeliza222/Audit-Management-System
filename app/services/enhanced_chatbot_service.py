"""
Enhanced Chatbot Service with Natural Language Database Querying
Integrates secure local AI for comprehensive database interactions
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
from flask import current_app, session
from sqlalchemy import func, and_, or_, text, desc, extract, asc
import psutil
import gc
import re
from collections import defaultdict

from app import db
from app.models import FAQ, User, Logs, DataDump, DraftFAQ
from app.audit_models import AuditQuery, Commitment
from app.utils.embeddings import get_bert_embeddings, normalize, find_related_questions_scored
from app.services.natural_language_db import NaturalLanguageDB


class EnhancedChatbotService:
    """Enhanced AI Assistant with natural language database querying capabilities"""
    
    def __init__(self):
        self.conversation_memory = ConversationMemory()
        self.app_knowledge = self._load_comprehensive_knowledge()
        self.nlp_processor = EnhancedNLPProcessor()
        self.natural_db = NaturalLanguageDB()
        
    def _load_comprehensive_knowledge(self) -> Dict:
        """Load comprehensive application knowledge base"""
        return {
            "application_overview": {
                "name": "Audit Management System",
                "purpose": "Comprehensive audit and data management platform",
                "main_features": [
                    "Audit workflow management",
                    "Data dump requests and approvals", 
                    "User management and access control",
                    "FAQ knowledge base",
                    "Real-time analytics and reporting",
                    "Natural language database querying"
                ]
            },
            "database_entities": {
                "FAQ": "Frequently Asked Questions and answers",
                "AuditQuery": "Audit queries and their responses",
                "DataDump": "Data dump requests and processing",
                "User": "User accounts and permissions",
                "Commitment": "Commitments made in responses",
                "DraftFAQ": "Draft FAQs awaiting review"
            },
            "query_capabilities": [
                "Count queries (how many)",
                "List queries (show me)",
                "Comparison queries (compare states)",
                "Status queries (pending, completed)",
                "Time-based queries (last 30 days)",
                "Aggregation queries (average, total)"
            ]
        }
    
    def process_message(self, message: str, state_name: str = None, user_id: str = None) -> Dict:
        """
        Process user message with enhanced natural language understanding
        
        Args:
            message: User's message
            state_name: Optional state context
            user_id: User identifier
            
        Returns:
            Dict containing response and metadata
        """
        try:
            # Get user role for access control
            user_role = self._get_user_role(user_id)
            
            # Analyze message intent
            intent_analysis = self.nlp_processor.analyze_intent(message)
            
            # Route to appropriate handler
            if intent_analysis["type"] == "database_query":
                result = self._handle_database_query(message, user_role, state_name)
            elif intent_analysis["type"] == "faq_query":
                result = self._handle_faq_query(message, state_name)
            elif intent_analysis["type"] == "general_help":
                result = self._handle_help_query(message, intent_analysis)
            elif intent_analysis["type"] == "greeting":
                result = self._handle_greeting(message)
            else:
                result = self._handle_general_query(message, intent_analysis)
            
            # Store conversation context
            self.conversation_memory.add_exchange(message, result["response"])
            
            # Add metadata
            result.update({
                "session_id": session.get("session_id", str(uuid.uuid4())),
                "intent_type": intent_analysis["type"],
                "confidence": intent_analysis.get("confidence", 0.5),
                "timestamp": datetime.utcnow().isoformat(),
                "user_role": user_role
            })
            
            return result
            
        except Exception as e:
            current_app.logger.error(f"Error processing message: {str(e)}")
            return {
                "response": "I'm sorry, I encountered an error while processing your request. Please try again.",
                "error": str(e),
                "query_type": "error"
            }
    
    def _get_user_role(self, user_id: str) -> str:
        """Get user role from database"""
        if not user_id:
            return "viewer"
        
        try:
            user = User.query.filter_by(id=user_id).first()
            return user.role if user else "viewer"
        except Exception:
            return "viewer"
    
    def _handle_database_query(self, message: str, user_role: str, state_name: str) -> Dict:
        """Handle natural language database queries"""
        try:
            # Use natural language DB service with proper error handling
            result = self.natural_db.understand_query(message, user_role)
            
            if "error" in result:
                return {
                    "response": result["error"],
                    "query_type": "database_error",
                    "suggestion": result.get("suggestion", "Try asking about counts or specific information")
                }
            
            return {
                "response": result["response"],
                "data": result.get("data"),
                "query_type": "database_query",
                "sources": result.get("sources", []),
                "confidence": result.get("confidence", 0.5)
            }
            
        except Exception as e:
            # Log error without using current_app (to avoid context issues)
            import logging
            logging.error(f"Database query error: {str(e)}")
            return {
                "response": "I couldn't process your database query. Please try rephrasing your question.",
                "query_type": "database_error"
            }
    
    def _handle_faq_query(self, message: str, state_name: str) -> Dict:
        """Handle FAQ-based queries using semantic search"""
        try:
            # Get question embedding
            question_embedding = get_bert_embeddings([message])[0]
            
            # Search for relevant FAQs
            relevant_faqs = find_related_questions_scored(
                question_embedding, 
                limit=5,
                state_filter=state_name
            )
            
            if not relevant_faqs:
                return {
                    "response": "I couldn't find a relevant answer in our knowledge base. Would you like me to search the database for you?",
                    "query_type": "faq_not_found",
                    "suggestion": "Try asking about specific data or counts"
                }
            
            # Get the best match
            best_faq = relevant_faqs[0]
            
            response = f"I found a relevant answer for you:\n\n{best_faq['answer']}"
            
            if len(relevant_faqs) > 1:
                response += f"\n\nConfidence: {best_faq['similarity']:.2f}"
            
            return {
                "response": response,
                "query_type": "faq_query",
                "sources": [f"FAQ ID: {best_faq['id']}"],
                "confidence": best_faq['similarity']
            }
            
        except Exception as e:
            current_app.logger.error(f"FAQ query error: {str(e)}")
            return {
                "response": "I had trouble searching the knowledge base. Let me try the database instead.",
                "query_type": "faq_error"
            }
    
    def _handle_help_query(self, message: str, intent_analysis: Dict) -> Dict:
        """Handle help and guidance queries"""
        help_topics = {
            "database": "I can help you query the database using natural language. Try asking:\n\n" +
                       "• 'How many FAQs are there?'\n" +
                       "• 'Show me data dump requests from Maharashtra'\n" +
                       "• 'What are the pending audit queries?'\n" +
                       "• 'Compare user counts by state'\n" +
                       "• 'How many commitments are overdue?'",
            
            "features": "I can help you with:\n\n" +
                       "• Natural language database queries\n" +
                       "• FAQ knowledge base search\n" +
                       "• System information and help\n" +
                       "• Data analysis and comparisons\n" +
                       "• Status and progress tracking",
            
            "general": "I'm your AI assistant for the Audit Management System. You can ask me questions about:\n\n" +
                      "• Database information (counts, lists, comparisons)\n" +
                      "• FAQ knowledge base\n" +
                      "• System features and help\n" +
                      "• Data analysis and reporting"
        }
        
        # Determine help topic
        message_lower = message.lower()
        if any(word in message_lower for word in ["database", "query", "data"]):
            topic = "database"
        elif any(word in message_lower for word in ["feature", "what can", "capabilities"]):
            topic = "features"
        else:
            topic = "general"
        
        return {
            "response": help_topics[topic],
            "query_type": "help",
            "confidence": 0.9
        }
    
    def _handle_greeting(self, message: str) -> Dict:
        """Handle greeting messages"""
        greetings = {
            "hello": "Hello! I'm your AI assistant for the Audit Management System. I can help you with database queries, FAQ searches, and system information. What would you like to know?",
            "hi": "Hi there! I'm here to help you with the Audit Management System. You can ask me questions about data, search the FAQ database, or get help with features. How can I assist you?",
            "good morning": "Good morning! I'm ready to help you with any questions about the Audit Management System. What can I do for you today?",
            "good afternoon": "Good afternoon! I'm here to assist you with the Audit Management System. Feel free to ask me anything about the database, FAQs, or system features.",
            "good evening": "Good evening! I'm your AI assistant for the Audit Management System. How can I help you today?"
        }
        
        message_lower = message.lower().strip()
        
        for greeting, response in greetings.items():
            if greeting in message_lower:
                return {
                    "response": response,
                    "query_type": "greeting",
                    "confidence": 0.95
                }
        
        return {
            "response": "Hello! I'm your AI assistant for the Audit Management System. I can help you with database queries, FAQ searches, and system information. What would you like to know?",
            "query_type": "greeting",
            "confidence": 0.8
        }
    
    def _handle_general_query(self, message: str, intent_analysis: Dict) -> Dict:
        """Handle general queries that don't fit other categories"""
        # Try to interpret as a database query as fallback
        try:
            user_role = self._get_user_role(session.get("user_id"))
            result = self.natural_db.understand_query(message, user_role)
            
            if "error" not in result:
                return {
                    "response": result["response"],
                    "data": result.get("data"),
                    "query_type": "database_query",
                    "sources": result.get("sources", []),
                    "confidence": result.get("confidence", 0.3)
                }
        except Exception:
            pass
        
        return {
            "response": "I'm not sure how to help with that. You can ask me about:\n\n" +
                      "• Database queries (e.g., 'How many users are there?')\n" +
                      "• FAQ searches (e.g., 'What are the audit procedures?')\n" +
                      "• System help (e.g., 'What can you do?')",
            "query_type": "general",
            "confidence": 0.2
        }


class EnhancedNLPProcessor:
    """Enhanced Natural Language Processing for intent analysis"""
    
    def __init__(self):
        self.intent_patterns = self._load_intent_patterns()
    
    def _load_intent_patterns(self) -> Dict:
        """Load patterns for intent recognition"""
        return {
            "database_query": [
                r"how many",
                r"number of",
                r"total",
                r"count",
                r"show me",
                r"list",
                r"display",
                r"what are",
                r"tell me about",
                r"compare",
                r"which",
                r"highest",
                r"lowest",
                r"pending",
                r"completed",
                r"overdue",
                r"recent"
            ],
            "faq_query": [
                r"what is",
                r"how to",
                r"procedure",
                r"process",
                r"guideline",
                r"policy",
                r"rule",
                r"requirement"
            ],
            "help_query": [
                r"help",
                r"what can",
                r"how do",
                r"feature",
                r"capability",
                r"assist",
                r"support"
            ],
            "greeting": [
                r"hello",
                r"hi",
                r"hey",
                r"good morning",
                r"good afternoon",
                r"good evening"
            ]
        }
    
    def analyze_intent(self, message: str) -> Dict:
        """Analyze user intent from message"""
        message_lower = message.lower().strip()
        
        # Check for greetings first
        for pattern in self.intent_patterns["greeting"]:
            if re.search(rf"\b{pattern}\b", message_lower):
                return {
                    "type": "greeting",
                    "confidence": 0.9,
                    "pattern": pattern
                }
        
        # Check for help queries
        for pattern in self.intent_patterns["help_query"]:
            if re.search(rf"\b{pattern}\b", message_lower):
                return {
                    "type": "general_help",
                    "confidence": 0.8,
                    "pattern": pattern
                }
        
        # Check for database queries
        db_matches = 0
        for pattern in self.intent_patterns["database_query"]:
            if re.search(rf"\b{pattern}\b", message_lower):
                db_matches += 1
        
        if db_matches >= 2:
            return {
                "type": "database_query",
                "confidence": min(0.9, 0.5 + (db_matches * 0.1)),
                "matches": db_matches
            }
        
        # Check for FAQ queries
        faq_matches = 0
        for pattern in self.intent_patterns["faq_query"]:
            if re.search(rf"\b{pattern}\b", message_lower):
                faq_matches += 1
        
        if faq_matches >= 1:
            return {
                "type": "faq_query",
                "confidence": min(0.8, 0.4 + (faq_matches * 0.2)),
                "matches": faq_matches
            }
        
        # Default to general query
        return {
            "type": "general",
            "confidence": 0.3
        }


class ConversationMemory:
    """Simple conversation memory for context tracking"""
    
    def __init__(self, max_exchanges: int = 10):
        self.exchanges = []
        self.max_exchanges = max_exchanges
    
    def add_exchange(self, user_message: str, bot_response: str):
        """Add conversation exchange to memory"""
        self.exchanges.append({
            "user": user_message,
            "bot": bot_response,
            "timestamp": datetime.utcnow()
        })
        
        # Keep only recent exchanges
        if len(self.exchanges) > self.max_exchanges:
            self.exchanges = self.exchanges[-self.max_exchanges:]
    
    def get_context(self, limit: int = 3) -> List[Dict]:
        """Get recent conversation context"""
        return self.exchanges[-limit:]
    
    def clear(self):
        """Clear conversation memory"""
        self.exchanges = []


# Factory function for dependency injection
def get_enhanced_chatbot_service():
    """Get enhanced chatbot service instance"""
    return EnhancedChatbotService()
