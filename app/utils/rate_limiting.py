"""
Enhanced rate limiting utilities for AMS
"""
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from flask import Flask, request, g, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis
from .logging_config import get_logger, security_logger
from .error_handlers import RateLimitError

logger = get_logger(__name__)


class RedisRateLimiter:
    """Redis-based rate limiter with advanced features"""
    
    def __init__(self, redis_url: str = None):
        self.redis_client = None
        if redis_url and redis_url != "memory://":
            try:
                self.redis_client = Redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                logger.info("Redis rate limiter initialized successfully")
            except Exception as e:
                logger.warning(f"Redis connection failed, falling back to memory: {e}")
                self.redis_client = None
    
    def is_allowed(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        """
        Check if request is allowed based on rate limit
        
        Args:
            key: Rate limit key (e.g., IP address, user ID)
            limit: Number of requests allowed
            window: Time window in seconds
        
        Returns:
            Dict with 'allowed', 'remaining', 'reset_time'
        """
        if not self.redis_client:
            # Fallback to simple in-memory limiting
            return self._memory_limit(key, limit, window)
        
        try:
            now = int(time.time())
            window_start = now - window
            
            # Use sliding window algorithm
            pipe = self.redis_client.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(now): now})
            
            # Set expiration
            pipe.expire(key, window)
            
            results = pipe.execute()
            current_requests = results[1]
            
            allowed = current_requests < limit
            remaining = max(0, limit - current_requests - 1)
            reset_time = now + window
            
            return {
                'allowed': allowed,
                'remaining': remaining,
                'reset_time': reset_time,
                'current': current_requests
            }
            
        except Exception as e:
            logger.error(f"Redis rate limiting error: {e}")
            # Fallback to memory limiting
            return self._memory_limit(key, limit, window)
    
    def _memory_limit(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        """Simple in-memory rate limiting fallback"""
        # This is a basic implementation - in production, use a proper cache
        if not hasattr(self, '_memory_store'):
            self._memory_store = {}
        
        now = time.time()
        
        if key not in self._memory_store:
            self._memory_store[key] = []
        
        # Remove old entries
        self._memory_store[key] = [
            timestamp for timestamp in self._memory_store[key]
            if now - timestamp < window
        ]
        
        current_requests = len(self._memory_store[key])
        allowed = current_requests < limit
        
        if allowed:
            self._memory_store[key].append(now)
        
        remaining = max(0, limit - current_requests - 1)
        reset_time = now + window
        
        return {
            'allowed': allowed,
            'remaining': remaining,
            'reset_time': reset_time,
            'current': current_requests
        }


class RateLimitConfig:
    """Rate limit configurations for different endpoints"""
    
    # General API limits
    DEFAULT_LIMIT = "200 per day, 50 per hour"
    AUTH_LIMIT = "100 per minute, 500 per hour"
    SEARCH_LIMIT = "30 per minute, 200 per hour"
    UPLOAD_LIMIT = "10 per minute, 50 per hour"
    ADMIN_LIMIT = "100 per minute, 1000 per hour"
    
    # Specific endpoint limits
    ENDPOINT_LIMITS = {
        'auth.login': "50 per minute, 200 per hour",
        'auth.register': "3 per minute, 10 per hour",
        'auth.reset_password': "3 per hour, 10 per day",
        'api.search': "30 per minute, 200 per hour",
        'api.upload': "10 per minute, 50 per hour",
        'api.export': "5 per minute, 20 per hour",
        'admin.*': "100 per minute, 1000 per hour"
    }


class AdvancedRateLimiter:
    """Advanced rate limiting with multiple strategies"""
    
    def __init__(self, app: Flask = None):
        self.app = app
        self.redis_limiter = None
        self.config = RateLimitConfig()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize rate limiter with Flask app"""
        self.app = app
        
        # Initialize Redis limiter
        redis_url = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
        self.redis_limiter = RedisRateLimiter(redis_url)
        
        # Register request hooks
        app.before_request(self._before_request)
        app.after_request(self._after_request)
    
    def _before_request(self):
        """Check rate limits before processing request"""
        if not request.endpoint:
            return
        
        # Skip rate limiting for static files and navigation
        if request.endpoint and (
            request.endpoint.startswith('static') or
            request.endpoint == 'auth.index' or
            request.method == 'GET'
        ):
            return
        
        # Get rate limit key
        key = self._get_rate_limit_key()
        
        # Get limit for endpoint
        limit_config = self._get_endpoint_limit(request.endpoint)
        
        # Check limits
        for limit_str in limit_config.split(','):
            limit_str = limit_str.strip()
            limit, window = self._parse_limit_string(limit_str)
            
            result = self.redis_limiter.is_allowed(key, limit, window)
            
            if not result['allowed']:
                # Log rate limit violation
                self._log_rate_limit_violation(key, limit_str, request.endpoint)
                
                # Raise rate limit error
                retry_after = int(result['reset_time'] - time.time())
                raise RateLimitError(
                    f"Rate limit exceeded: {limit_str}",
                    retry_after=retry_after
                )
            
            # Add rate limit headers
            g.rate_limit_result = result
    
    def _after_request(self, response):
        """Add rate limit headers to response"""
        if hasattr(g, 'rate_limit_result'):
            result = g.rate_limit_result
            response.headers['X-RateLimit-Limit'] = str(result.get('current', 0) + result.get('remaining', 0))
            response.headers['X-RateLimit-Remaining'] = str(result.get('remaining', 0))
            response.headers['X-RateLimit-Reset'] = str(int(result.get('reset_time', 0)))
        
        return response
    
    def _get_rate_limit_key(self) -> str:
        """Generate rate limit key based on request context"""
        # Priority: user ID > IP address
        if hasattr(g, 'user_id') and g.user_id:
            return f"user:{g.user_id}"
        else:
            return f"ip:{get_remote_address()}"
    
    def _get_endpoint_limit(self, endpoint: str) -> str:
        """Get rate limit configuration for endpoint"""
        # Check specific endpoint limits
        for pattern, limit in self.config.ENDPOINT_LIMITS.items():
            if self._match_endpoint(endpoint, pattern):
                return limit
        
        # Check if it's an admin endpoint
        if endpoint and endpoint.startswith('admin.'):
            return self.config.ADMIN_LIMIT
        
        # Check if it's an auth endpoint
        if endpoint and endpoint.startswith('auth.'):
            return self.config.AUTH_LIMIT
        
        # Default limit
        return self.config.DEFAULT_LIMIT
    
    def _match_endpoint(self, endpoint: str, pattern: str) -> bool:
        """Check if endpoint matches pattern"""
        if pattern.endswith('.*'):
            return endpoint.startswith(pattern[:-1])
        else:
            return endpoint == pattern
    
    def _parse_limit_string(self, limit_str: str) -> tuple:
        """Parse limit string like '50 per hour' into (limit, window_seconds)"""
        parts = limit_str.lower().split()
        if len(parts) != 3 or parts[1] != 'per':
            raise ValueError(f"Invalid limit format: {limit_str}")
        
        limit = int(parts[0])
        period = parts[2]
        
        # Convert period to seconds
        period_map = {
            'second': 1,
            'minute': 60,
            'hour': 3600,
            'day': 86400,
            'week': 604800,
            'month': 2592000
        }
        
        window = period_map.get(period, 3600)  # Default to hour
        
        return limit, window
    
    def _log_rate_limit_violation(self, key: str, limit: str, endpoint: str):
        """Log rate limit violations"""
        security_logger.log_suspicious_activity(
            f"Rate limit exceeded on {endpoint}",
            {
                'key': key,
                'limit': limit,
                'endpoint': endpoint,
                'user_agent': str(request.user_agent) if request else None,
                'ip_address': getattr(g, 'ip_address', None)
            }
        )


class RateLimitMiddleware:
    """Middleware for rate limiting"""
    
    def __init__(self, app: Flask = None):
        self.advanced_limiter = AdvancedRateLimiter()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize middleware with Flask app"""
        self.advanced_limiter.init_app(app)
        
        # Register error handler
        app.register_error_handler(RateLimitError, self._handle_rate_limit_error)
    
    def _handle_rate_limit_error(self, error: RateLimitError):
        """Handle rate limit errors"""
        response = {
            'error': {
                'code': 'RATE_LIMIT_EXCEEDED',
                'message': error.message,
                'retry_after': error.details.get('retry_after') if error.details else None
            }
        }
        
        headers = {}
        if error.details and 'retry_after' in error.details:
            headers['Retry-After'] = str(error.details['retry_after'])
        
        return response, 429, headers


# Global rate limiter instance
rate_limiter = RateLimitMiddleware()


def rate_limit(limit: str, key_func=None):
    """Decorator for rate limiting specific functions"""
    def decorator(f):
        from functools import wraps
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get rate limit key
            if key_func:
                key = key_func()
            else:
                key = rate_limiter.advanced_limiter._get_rate_limit_key()
            
            # Parse limit
            if rate_limiter.advanced_limiter.redis_limiter is not None:
                limiter = rate_limiter.advanced_limiter.redis_limiter
            else:
                # Use memory fallback
                limiter = rate_limiter.advanced_limiter
            limit_val, window = rate_limiter.advanced_limiter._parse_limit_string(limit)
            
            # Check limit
            result = limiter.is_allowed(key, limit_val, window)
            
            if not result['allowed']:
                retry_after = int(result['reset_time'] - time.time())
                raise RateLimitError(f"Rate limit exceeded: {limit}", retry_after)
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def get_rate_limit_status() -> Dict[str, Any]:
    """Get current rate limit status"""
    if hasattr(g, 'rate_limit_result'):
        return g.rate_limit_result
    return None


def reset_rate_limit(key: str) -> bool:
    """Reset rate limit for a specific key"""
    try:
        if rate_limiter.advanced_limiter.redis_limiter.redis_client:
            return rate_limiter.advanced_limiter.redis_limiter.redis_client.delete(key) > 0
        return False
    except Exception as e:
        logger.error(f"Failed to reset rate limit for key {key}: {e}")
        return False


def rate_limit_check(limit: int, window: int, key_func=None):
    """
    Rate limiting decorator function for document QA endpoints
    
    Args:
        limit: Number of requests allowed
        window: Time window in seconds
        key_func: Function to generate rate limit key (defaults to IP address)
    
    Returns:
        Decorator function
    """
    def decorator(f):
        import functools
        
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Get key for rate limiting
            if key_func:
                key = key_func()
            else:
                key = get_remote_address()
            
            # Check rate limit
            result = rate_limiter.advanced_limiter.redis_limiter.is_allowed(key, limit, window)
            
            if not result.get('allowed', True):
                raise RateLimitError(f"Rate limit exceeded. Try again in {result.get('reset_time', 60)} seconds.")
            
            # Store result in flask g for access
            g.rate_limit_result = result
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator
