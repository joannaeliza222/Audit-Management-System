"""
LLM-based Response Generator for Natural Chatbot Interactions
Uses transformers library to generate intelligent, contextual responses
"""

import os
import torch
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from flask import current_app
import re

class LLMResponseGenerator:
    """Intelligent response generator using local LLM"""
    
    def __init__(self):
        self.model_name = os.getenv("LLM_MODEL_NAME", "microsoft/DialoGPT-medium")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = None
        self.model = None
        self.generator = None
        self.conversation_history = []
        self.max_history = 5
        
        # Response templates for different contexts
        self.response_templates = self._load_response_templates()
    
    def _load_response_templates(self) -> Dict:
        """Load response templates for different query types"""
        return {
            'state_query': {
                'system_prompt': "You are a helpful AI assistant for an Audit Management System. The user is asking about state-specific data. Provide a clear, natural response based on the data provided.",
                'response_format': "Based on the current data, {state} has {approved_faqs} approved FAQs{draft_info}. There are {users} registered users and {dump_requests} data dump requests from {state}."
            },
            'comparison_query': {
                'system_prompt': "You are a helpful AI assistant for an Audit Management System. The user is asking for a comparison between states. Provide a natural, comparative response.",
                'response_format': "Looking at the data, {top_state} leads with {top_count} FAQs, followed by {second_state} with {second_count} FAQs. {additional_info}"
            },
            'general_query': {
                'system_prompt': "You are a helpful AI assistant for an Audit Management System. Provide a helpful, natural response to the user's question.",
                'response_format': "I can help you with that. {response}"
            },
            'faq_query': {
                'system_prompt': "You are a helpful AI assistant for an Audit Management System. The user asked a question and I found a relevant answer in the knowledge base. Present this information naturally.",
                'response_format': "I found a relevant answer for you: {answer}"
            },
            'greeting': {
                'system_prompt': "You are a friendly AI assistant for an Audit Management System. Respond naturally to greetings.",
                'responses': [
                    "Hello! I'm here to help you with the Audit Management System. What would you like to know?",
                    "Hi there! I can assist you with questions about audits, data, and system information. How can I help?",
                    "Welcome! I'm your AI assistant for the Audit Management System. What can I do for you today?"
                ]
            }
        }
    
    def initialize_model(self):
        """Initialize the LLM model and tokenizer"""
        try:
            if self.generator is None:
                current_app.logger.info(f"Loading LLM model: {self.model_name}")
                
                # Use a lighter model for better performance
                model_name = "microsoft/DialoGPT-small"  # Smaller model for faster responses
                
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModelForCausalLM.from_pretrained(model_name)
                
                # Move to device
                self.model.to(self.device)
                
                # Create text generation pipeline
                self.generator = pipeline(
                    'text-generation',
                    model=self.model,
                    tokenizer=self.tokenizer,
                    device=0 if self.device.type == 'cuda' else -1,
                    max_length=200,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id
                )
                
                current_app.logger.info("LLM model loaded successfully")
                
        except Exception as e:
            # Handle Flask context issue
            try:
                current_app.logger.error(f"Failed to load LLM model: {e}")
            except RuntimeError:
                # No Flask context available - use standard logging
                import logging
                logging.error(f"Failed to load LLM model: {e}")
            # Fallback to template-based responses
            self.generator = None
    
    def generate_response(self, user_message: str, query_data: Dict = None, context: Dict = None) -> Dict:
        """Generate intelligent response using LLM"""
        
        try:
            # Initialize model if needed
            if self.generator is None:
                self.initialize_model()
            
            # Determine query type
            query_type = self._classify_query_type(user_message, query_data)
            
            # Generate response based on type and data
            if query_type == 'state_specific' and query_data:
                response = self._generate_state_response(user_message, query_data, context)
            elif query_type == 'comparison' and query_data:
                response = self._generate_comparison_response(user_message, query_data, context)
            elif query_type == 'faq_query' and query_data:
                response = self._generate_faq_response(user_message, query_data, context)
            elif query_type == 'greeting':
                response = self._generate_greeting_response()
            else:
                response = self._generate_general_response(user_message, query_data, context)
            
            # Update conversation history
            self._update_history(user_message, response['response'])
            
            return response
            
        except Exception as e:
            # Handle Flask context issue
            try:
                current_app.logger.error(f"LLM response generation error: {e}")
            except RuntimeError:
                # No Flask context available - use standard logging
                import logging
                logging.error(f"LLM response generation error: {e}")
            
            return self._fallback_response(user_message, query_data)
    
    def _classify_query_type(self, message: str, query_data: Dict = None) -> str:
        """Classify the type of query"""
        message_lower = message.lower()
        
        # Check for greetings
        greeting_words = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'help']
        if any(word in message_lower for word in greeting_words):
            return 'greeting'
        
        # Check for FAQ-related queries
        if query_data and 'faq_result' in query_data:
            return 'faq_query'
        
        # Check for no FAQ found
        if query_data and query_data.get('no_faq_found'):
            return 'general_query'
        
        # Check for state-specific queries
        if query_data and 'state_statistics' in query_data:
            state_keywords = ['tn', 'tamil nadu', 'punjab', 'haryana', 'delhi', 'state']
            if any(keyword in message_lower for keyword in state_keywords):
                return 'state_specific'
        
        # Check for comparison queries
        comparison_keywords = ['which state', 'compare', 'most', 'highest', 'lowest', 'better', 'versus', 'vs']
        if any(keyword in message_lower for keyword in comparison_keywords):
            return 'comparison'
        
        return 'general_query'
    
    def _generate_state_response(self, message: str, query_data: Dict, context: Dict = None) -> Dict:
        """Generate response for state-specific queries"""
        
        try:
            # Extract state information
            state_stats = query_data.get('state_statistics', {})
            query_params = query_data.get('query_params', {})
            specific_state = query_params.get('specific_state')
            
            if specific_state and specific_state in state_stats:
                # Response for specific state
                stats = state_stats[specific_state]
                is_admin = query_data.get('is_admin', False)
                
                # Create natural response
                response = f"{specific_state} has {stats['approved_faqs']} approved FAQs"
                
                if is_admin and stats['draft_faqs'] > 0:
                    response += f" and {stats['draft_faqs']} draft FAQs"
                
                if stats['users'] > 0:
                    response += f". There are {stats['users']} registered users"
                
                if stats['dump_requests'] > 0:
                    response += f" and {stats['dump_requests']} data dump requests"
                
                response += f" from {specific_state}."
                
                # Add contextual information
                if not is_admin and stats['draft_faqs'] > 0:
                    response += " Additional FAQs are currently pending review."
                
            else:
                # General state overview
                total_states = query_data.get('total_states', 0)
                response = f"The system has data for {total_states} active states. "
                
                # Find top state
                if state_stats:
                    top_state = max(state_stats.items(), key=lambda x: x[1]['approved_faqs'])
                    response += f"{top_state[0]} has the most approved FAQs with {top_state[1]['approved_faqs']}."
            
            # Use LLM to make response more natural if available
            if self.generator:
                natural_response = self._enhance_response_with_llm(message, response, 'state_query')
                if natural_response:
                    response = natural_response
            
            return {
                'response': response,
                'confidence': 0.9,
                'source': 'llm_enhanced',
                'query_type': 'state_specific',
                'data_used': query_data
            }
            
        except Exception as e:
            current_app.logger.error(f"State response generation error: {e}")
            return self._fallback_response(message, query_data)
    
    def _generate_comparison_response(self, message: str, query_data: Dict, context: Dict = None) -> Dict:
        """Generate response for comparison queries"""
        
        try:
            state_stats = query_data.get('state_statistics', {})
            
            if not state_stats:
                return {
                    'response': "I don't have sufficient data to make that comparison.",
                    'confidence': 0.3,
                    'source': 'fallback'
                }
            
            # Sort states by FAQ count
            sorted_states = sorted(state_stats.items(), key=lambda x: x[1]['approved_faqs'], reverse=True)
            
            # Create comparison response
            top_states = sorted_states[:3]
            
            response = "Based on the current data: "
            response += f"{top_states[0][0]} leads with {top_states[0][1]['approved_faqs']} approved FAQs"
            
            if len(top_states) > 1:
                response += f", followed by {top_states[1][0]} with {top_states[1][1]['approved_faqs']}"
            
            if len(top_states) > 2:
                response += f", and {top_states[2][0]} with {top_states[2][1]['approved_faqs']}"
            
            response += "."
            
            # Use LLM to enhance if available
            if self.generator:
                natural_response = self._enhance_response_with_llm(message, response, 'comparison_query')
                if natural_response:
                    response = natural_response
            
            return {
                'response': response,
                'confidence': 0.85,
                'source': 'llm_enhanced',
                'query_type': 'comparison',
                'data_used': query_data
            }
            
        except Exception as e:
            current_app.logger.error(f"Comparison response generation error: {e}")
            return self._fallback_response(message, query_data)
    
    def _generate_faq_response(self, message: str, query_data: Dict, context: Dict = None) -> Dict:
        """Generate response for FAQ queries"""
        
        try:
            faq_result = query_data.get('faq_result', {})
            
            if not faq_result:
                return self._fallback_response(message, query_data)
            
            # Extract FAQ information
            question = faq_result.get('question', '')
            answer = faq_result.get('answer', '')
            score = faq_result.get('score', 0)
            related_questions = faq_result.get('related_questions', [])
            
            # Create natural response
            response = f"I found a relevant answer for your question."
            
            if answer and len(answer.strip()) > 0:
                response += f" {answer}"
            else:
                response += " Unfortunately, the specific answer isn't available, but this question was found in our knowledge base."
            
            # Add related questions if available
            if related_questions:
                response += "\n\nRelated questions you might find helpful:"
                for i, related in enumerate(related_questions[:3], 1):
                    related_q = related.get('question', '')
                    if related_q:
                        response += f"\n{i}. {related_q}"
            
            # Use LLM to enhance if available
            if self.generator:
                enhanced = self._enhance_response_with_llm(message, response, 'faq_query')
                if enhanced:
                    response = enhanced
            
            return {
                'response': response,
                'confidence': score,
                'source': 'llm_enhanced',
                'query_type': 'faq_query',
                'faq_data': faq_result
            }
            
        except Exception as e:
            current_app.logger.error(f"FAQ response generation error: {e}")
            return self._fallback_response(message, query_data)
    
    def _generate_greeting_response(self) -> Dict:
        """Generate natural greeting response"""
        
        try:
            greetings = self.response_templates['greeting']['responses']
            import random
            response = random.choice(greetings)
            
            # Use LLM to make it more conversational if available
            if self.generator:
                enhanced = self._enhance_response_with_llm("hello", response, 'greeting')
                if enhanced:
                    response = enhanced
            
            return {
                'response': response,
                'confidence': 0.95,
                'source': 'llm_enhanced',
                'query_type': 'greeting'
            }
            
        except Exception as e:
            current_app.logger.error(f"Greeting response error: {e}")
            return {
                'response': "Hello! I'm here to help you with the Audit Management System. What would you like to know?",
                'confidence': 0.8,
                'source': 'fallback'
            }
    
    def _generate_general_response(self, message: str, query_data: Dict = None, context: Dict = None) -> Dict:
        """Generate general response"""
        
        try:
            # Check if we have relevant data
            if query_data:
                # Try to extract useful information from query_data
                if 'total_states' in query_data:
                    response = f"The system currently has {query_data['total_states']} active states with various audit and FAQ data."
                elif 'state_statistics' in query_data:
                    total_faqs = sum(stats['approved_faqs'] for stats in query_data['state_statistics'].values())
                    response = f"There are {total_faqs} approved FAQs across all states in the system."
                else:
                    response = "I can help you with information about the Audit Management System, including state-specific data, FAQs, and user statistics."
            else:
                response = "I'm here to help you with the Audit Management System. You can ask me about state statistics, FAQ data, or system information."
            
            # Use LLM to enhance if available
            if self.generator:
                enhanced = self._enhance_response_with_llm(message, response, 'general_query')
                if enhanced:
                    response = enhanced
            
            return {
                'response': response,
                'confidence': 0.7,
                'source': 'llm_enhanced',
                'query_type': 'general',
                'data_used': query_data
            }
            
        except Exception as e:
            current_app.logger.error(f"General response error: {e}")
            return self._fallback_response(message, query_data)
    
    def _enhance_response_with_llm(self, user_message: str, base_response: str, response_type: str) -> Optional[str]:
        """Use LLM to enhance the base response"""
        
        try:
            if not self.generator:
                return None
            
            # Create prompt based on response type
            template = self.response_templates.get(response_type, self.response_templates['general_query'])
            system_prompt = template.get('system_prompt', "You are a helpful AI assistant.")
            
            # Create context for the LLM
            prompt = f"{system_prompt}\n\nUser: {user_message}\nBase response: {base_response}\n\nGenerate a more natural, conversational response:"
            
            # Generate enhanced response
            outputs = self.generator(
                prompt,
                max_new_tokens=100,
                temperature=0.7,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                num_return_sequences=1
            )
            
            if outputs and len(outputs) > 0:
                generated_text = outputs[0]['generated_text']
                
                # Extract the generated part (after the prompt)
                if prompt in generated_text:
                    enhanced = generated_text.replace(prompt, "").strip()
                    # Clean up the response
                    enhanced = re.sub(r'^[^a-zA-Z]*', '', enhanced)  # Remove leading non-letters
                    enhanced = enhanced.split('\n')[0]  # Take first line
                    
                    if len(enhanced) > 10:  # Ensure we got a meaningful response
                        return enhanced
            
            return None
            
        except Exception as e:
            current_app.logger.error(f"LLM enhancement error: {e}")
            return None
    
    def _update_history(self, user_message: str, bot_response: str):
        """Update conversation history"""
        self.conversation_history.append({
            'user': user_message,
            'bot': bot_response,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Keep only recent history
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
    
    def _fallback_response(self, message: str, query_data: Dict = None) -> Dict:
        """Fallback response when LLM fails"""
        
        # Simple template-based fallback
        if query_data and 'state_statistics' in query_data:
            return {
                'response': "I can help you with state-specific information. Please ask about a particular state or general statistics.",
                'confidence': 0.5,
                'source': 'fallback'
            }
        else:
            return {
                'response': "I'm here to help with the Audit Management System. You can ask me about state data, FAQs, or system information.",
                'confidence': 0.5,
                'source': 'fallback'
            }
    
    def get_model_info(self) -> Dict:
        """Get information about the loaded model"""
        return {
            'model_name': self.model_name,
            'device': str(self.device),
            'model_loaded': self.generator is not None,
            'conversation_history_length': len(self.conversation_history)
        }
