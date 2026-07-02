"""
LLM QA Service
Provides LLM model management for document Q&A functionality
"""

import os
import logging
from typing import Dict, List, Optional
from flask import current_app

logger = logging.getLogger(__name__)


class LLMQAService:
    """Service for managing LLM models for document Q&A"""
    
    def __init__(self):
        self.default_model = "gpt-3.5-turbo"
        self.available_models = [
            "gpt-3.5-turbo",
            "gpt-4",
            "gpt-4-turbo",
            "claude-3-sonnet",
            "claude-3-opus"
        ]
    
    def get_available_models(self) -> List[str]:
        """Get list of available LLM models"""
        try:
            # Check which models are actually available based on API keys
            models = []
            
            # Check OpenAI models
            if os.getenv('OPENAI_API_KEY'):
                models.extend(["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"])
            
            # Check Claude models
            if os.getenv('CLAUDE_API_KEY'):
                models.extend(["claude-3-sonnet", "claude-3-opus"])
            
            # If no API keys configured, return default list
            if not models:
                logger.warning("No API keys configured, returning default model list")
                return [self.default_model]
            
            return models
            
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return [self.default_model]
    
    def validate_api_keys(self) -> Dict[str, bool]:
        """Validate configured API keys"""
        status = {
            'openai': False,
            'claude': False
        }
        
        try:
            # Check OpenAI API key
            openai_key = os.getenv('OPENAI_API_KEY')
            if openai_key and len(openai_key) > 20:  # Basic validation
                status['openai'] = True
            
            # Check Claude API key
            claude_key = os.getenv('CLAUDE_API_KEY')
            if claude_key and len(claude_key) > 20:  # Basic validation
                status['claude'] = True
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to validate API keys: {e}")
            return status
