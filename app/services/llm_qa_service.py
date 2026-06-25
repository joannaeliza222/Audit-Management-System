import os
import json
import logging
from typing import List, Dict, Tuple, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMQAService:
    """LLM integration service for document Q&A"""
    
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        self.default_model = os.getenv('LLM_MODEL', 'gpt-3.5-turbo')
        self.max_tokens = int(os.getenv('LLM_MAX_TOKENS', '1000'))
        self.temperature = float(os.getenv('LLM_TEMPERATURE', '0.1'))
        
        # Context window limits for different models
        self.context_limits = {
            'gpt-3.5-turbo': 4096,
            'gpt-4': 8192,
            'gpt-4-turbo': 128000,
            'claude-3-sonnet': 200000,
            'claude-3-opus': 200000,
        }
    
    def generate_answer(self, question: str, context_chunks: List[str], 
                       model: str = None, user_id: int = None) -> Tuple[str, float]:
        """Generate answer using LLM"""
        model = model or self.default_model
        
        try:
            if model.startswith('gpt') and self.openai_api_key:
                return self._generate_openai_answer(question, context_chunks, model)
            elif model.startswith('claude') and self.anthropic_api_key:
                return self._generate_anthropic_answer(question, context_chunks, model)
            else:
                # Fallback to local generation
                return self._generate_local_answer(question, context_chunks)
                
        except Exception as e:
            logger.error(f"LLM answer generation failed: {e}")
            return self._generate_local_answer(question, context_chunks)
    
    def _generate_openai_answer(self, question: str, context_chunks: List[str], 
                               model: str) -> Tuple[str, float]:
        """Generate answer using OpenAI API"""
        try:
            # Prepare context
            context = self._prepare_context(context_chunks, model)
            
            # Create prompt
            system_prompt = self._get_system_prompt()
            user_prompt = self._format_user_prompt(question, context)
            
            # Make API request
            headers = {
                'Authorization': f'Bearer {self.openai_api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'max_tokens': self.max_tokens,
                'temperature': self.temperature,
                'stream': False
            }
            
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data['choices'][0]['message']['content']
                confidence = self._calculate_confidence(data)
                return answer, confidence
            else:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                raise Exception(f"OpenAI API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"OpenAI answer generation failed: {e}")
            raise
    
    def _generate_anthropic_answer(self, question: str, context_chunks: List[str], 
                                  model: str) -> Tuple[str, float]:
        """Generate answer using Anthropic Claude API"""
        try:
            # Prepare context
            context = self._prepare_context(context_chunks, model)
            
            # Create prompt
            system_prompt = self._get_system_prompt()
            user_prompt = self._format_user_prompt(question, context)
            
            # Make API request
            headers = {
                'x-api-key': self.anthropic_api_key,
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01'
            }
            
            payload = {
                'model': model,
                'max_tokens': self.max_tokens,
                'temperature': self.temperature,
                'system': system_prompt,
                'messages': [
                    {'role': 'user', 'content': user_prompt}
                ]
            }
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data['content'][0]['text']
                confidence = self._calculate_confidence_anthropic(data)
                return answer, confidence
            else:
                logger.error(f"Anthropic API error: {response.status_code} - {response.text}")
                raise Exception(f"Anthropic API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Anthropic answer generation failed: {e}")
            raise
    
    def _generate_local_answer(self, question: str, context_chunks: List[str]) -> Tuple[str, float]:
        """Generate answer using local processing (fallback)"""
        try:
            context = "\n\n".join(context_chunks)
            
            # Simple rule-based answer generation
            answer = f"Based on the document content provided:\n\n{context[:800]}..."
            
            if len(context) > 800:
                answer += f"\n\nNote: This is a partial response. The document contains more relevant information."
            
            confidence = 0.6  # Lower confidence for local generation
            return answer, confidence
            
        except Exception as e:
            logger.error(f"Local answer generation failed: {e}")
            return "I'm sorry, I couldn't generate an answer from the provided context.", 0.0
    
    def _prepare_context(self, context_chunks: List[str], model: str) -> str:
        """Prepare context within model's token limit"""
        context_limit = self.context_limits.get(model, 4096)
        
        # Reserve tokens for system prompt and question
        reserved_tokens = 1000
        available_tokens = context_limit - reserved_tokens
        
        # Simple token estimation (rough approximation: 1 token ≈ 4 characters)
        available_chars = available_tokens * 4
        
        context = ""
        for chunk in context_chunks:
            if len(context) + len(chunk) + 2 <= available_chars:  # +2 for \n\n
                context += chunk + "\n\n"
            else:
                # Add partial chunk if space allows
                remaining_space = available_chars - len(context) - 2
                if remaining_space > 100:  # Only add if meaningful space remains
                    context += chunk[:remaining_space]
                break
        
        return context.strip()
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM"""
        return """You are a helpful AI assistant specialized in answering questions about uploaded documents. 

Your task is to:
1. Answer the user's question based ONLY on the provided document context
2. Be accurate, concise, and helpful
3. If the context doesn't contain enough information to answer the question, say so clearly
4. Cite the relevant parts of the document when possible
5. Do not make up information or use external knowledge
6. If you're uncertain about the answer, indicate your confidence level

Format your response in a clear, professional manner."""
    
    def _format_user_prompt(self, question: str, context: str) -> str:
        """Format user prompt with context and question"""
        return f"""Document Context:
{context}

Question: {question}

Please answer the question based only on the document context provided above. If the context doesn't contain sufficient information to answer the question, please indicate that clearly."""
    
    def _calculate_confidence(self, response_data: Dict) -> float:
        """Calculate confidence score from OpenAI response"""
        try:
            # Use logprobs if available, otherwise default to high confidence
            if 'choices' in response_data and len(response_data['choices']) > 0:
                choice = response_data['choices'][0]
                if 'logprobs' in choice and choice['logprobs']:
                    # Calculate average probability
                    logprobs = choice['logprobs'].get('token_logprobs', [])
                    if logprobs:
                        avg_logprob = sum(logprobs) / len(logprobs)
                        confidence = min(max(avg_logprob + 1, 0), 1)  # Normalize to 0-1
                        return confidence
            
            return 0.8  # Default confidence
            
        except Exception as e:
            logger.error(f"Confidence calculation failed: {e}")
            return 0.5
    
    def _calculate_confidence_anthropic(self, response_data: Dict) -> float:
        """Calculate confidence score from Anthropic response"""
        try:
            # Anthropic doesn't provide logprobs in the same way
            # Use stop_reason as a proxy for confidence
            stop_reason = response_data.get('stop_reason', '')
            
            if stop_reason == 'end_turn':
                return 0.9  # High confidence - natural completion
            elif stop_reason == 'max_tokens':
                return 0.6  # Lower confidence - cut off
            else:
                return 0.8  # Default confidence
                
        except Exception as e:
            logger.error(f"Anthropic confidence calculation failed: {e}")
            return 0.5
    
    def get_available_models(self) -> List[Dict[str, str]]:
        """Get list of available models"""
        models = []
        
        if self.openai_api_key:
            models.extend([
                {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'provider': 'OpenAI'},
                {'id': 'gpt-4', 'name': 'GPT-4', 'provider': 'OpenAI'},
                {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo', 'provider': 'OpenAI'},
            ])
        
        if self.anthropic_api_key:
            models.extend([
                {'id': 'claude-3-sonnet', 'name': 'Claude 3 Sonnet', 'provider': 'Anthropic'},
                {'id': 'claude-3-opus', 'name': 'Claude 3 Opus', 'provider': 'Anthropic'},
            ])
        
        # Always include local option
        models.append({'id': 'local', 'name': 'Local Processing', 'provider': 'Local'})
        
        return models
    
    def validate_api_keys(self) -> Dict[str, bool]:
        """Validate API keys"""
        return {
            'openai': bool(self.openai_api_key),
            'anthropic': bool(self.anthropic_api_key)
        }
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)"""
        # Simple estimation: 1 token ≈ 4 characters for English text
        return len(text) // 4
    
    def truncate_context(self, context: str, model: str, reserve_tokens: int = 1000) -> str:
        """Truncate context to fit within model's token limit"""
        context_limit = self.context_limits.get(model, 4096)
        available_tokens = context_limit - reserve_tokens
        max_chars = available_tokens * 4
        
        if len(context) <= max_chars:
            return context
        
        # Try to truncate at sentence boundary
        truncated = context[:max_chars]
        
        # Find last sentence boundary
        for i in range(len(truncated) - 1, max(len(truncated) - 200, 0), -1):
            if truncated[i] in '.!?':
                return truncated[:i + 1]
        
        # Fallback: truncate at word boundary
        for i in range(len(truncated) - 1, max(len(truncated) - 100, 0), -1):
            if truncated[i] == ' ':
                return truncated[:i] + '...'
        
        return truncated[:max_chars] + '...'
    
    def get_model_info(self, model: str) -> Dict:
        """Get information about a specific model"""
        model_info = {
            'id': model,
            'context_limit': self.context_limits.get(model, 4096),
            'provider': 'Unknown'
        }
        
        if model.startswith('gpt'):
            model_info['provider'] = 'OpenAI'
        elif model.startswith('claude'):
            model_info['provider'] = 'Anthropic'
        elif model == 'local':
            model_info['provider'] = 'Local'
        
        return model_info
