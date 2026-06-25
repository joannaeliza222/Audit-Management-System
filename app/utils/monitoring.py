"""
Monitoring and metrics utilities for AMS
"""
import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
from flask import Flask, request, g, current_app
from sqlalchemy import text
from app import db
from .logging_config import get_logger, audit_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Collects and stores application metrics"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics = defaultdict(lambda: deque(maxlen=max_history))
        self.counters = defaultdict(int)
        self.start_time = time.time()
        self._lock = threading.Lock()
    
    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record a metric value"""
        with self._lock:
            timestamp = time.time()
            self.metrics[name].append({
                'timestamp': timestamp,
                'value': value,
                'tags': tags or {}
            })
    
    def increment_counter(self, name: str, value: int = 1, tags: Dict[str, str] = None):
        """Increment a counter"""
        with self._lock:
            key = f"{name}:{hash(str(tags))}" if tags else name
            self.counters[key] += value
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        with self._lock:
            summary = {}
            
            # Process metrics
            for name, values in self.metrics.items():
                if not values:
                    continue
                
                recent_values = [v['value'] for v in list(values)[-100:]]  # Last 100 values
                
                summary[name] = {
                    'count': len(values),
                    'latest': values[-1]['value'],
                    'avg': sum(recent_values) / len(recent_values),
                    'min': min(recent_values),
                    'max': max(recent_values),
                    'last_updated': values[-1]['timestamp']
                }
            
            # Add counters
            summary['counters'] = dict(self.counters)
            
            # Add system info
            summary['system'] = self.get_system_metrics()
            
            return summary
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system-level metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            
            # Process metrics
            process = psutil.Process()
            process_memory = process.memory_info()
            
            return {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'memory_total': memory.total,
                'memory_available': memory.available,
                'memory_percent': memory.percent,
                'disk_total': disk.total,
                'disk_used': disk.used,
                'disk_percent': (disk.used / disk.total) * 100,
                'process_memory_rss': process_memory.rss,
                'process_memory_vms': process_memory.vms,
                'uptime': time.time() - self.start_time
            }
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            return {}
    
    def reset_metrics(self):
        """Reset all metrics"""
        with self._lock:
            self.metrics.clear()
            self.counters.clear()
            self.start_time = time.time()


class DatabaseMonitor:
    """Database performance monitoring"""
    
    def __init__(self):
        self.query_times = deque(maxlen=1000)
        self.query_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
    
    def record_query(self, query: str, duration: float, success: bool = True):
        """Record database query metrics"""
        self.query_times.append(duration)
        
        # Extract table name from query (simplified)
        table = self._extract_table_name(query)
        
        if success:
            self.query_counts[table] += 1
        else:
            self.error_counts[table] += 1
    
    def _extract_table_name(self, query: str) -> str:
        """Extract table name from SQL query"""
        query_lower = query.lower().strip()
        
        if query_lower.startswith('select'):
            # Find FROM clause
            from_match = query_lower.find('from')
            if from_match != -1:
                from_part = query_lower[from_match + 4:].strip()
                table = from_part.split()[0]
                return table.strip('`"[]')
        elif query_lower.startswith('insert'):
            # Find INTO clause
            into_match = query_lower.find('into')
            if into_match != -1:
                into_part = query_lower[into_match + 4:].strip()
                table = into_part.split()[0]
                return table.strip('`"[]')
        elif query_lower.startswith('update'):
            # Table name comes after UPDATE
            table = query_lower[6:].strip().split()[0]
            return table.strip('`"[]')
        elif query_lower.startswith('delete'):
            # Find FROM clause
            from_match = query_lower.find('from')
            if from_match != -1:
                from_part = query_lower[from_match + 4:].strip()
                table = from_part.split()[0]
                return table.strip('`"[]')
        
        return 'unknown'
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get database performance metrics"""
        if not self.query_times:
            return {}
        
        return {
            'avg_query_time': sum(self.query_times) / len(self.query_times),
            'max_query_time': max(self.query_times),
            'min_query_time': min(self.query_times),
            'total_queries': len(self.query_times),
            'query_counts': dict(self.query_counts),
            'error_counts': dict(self.error_counts),
            'error_rate': sum(self.error_counts.values()) / len(self.query_times) if self.query_times else 0
        }


class HealthChecker:
    """Application health checking"""
    
    def __init__(self, app: Flask = None):
        self.app = app
        self.checks = {}
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize health checker with Flask app"""
        self.app = app
        
        # Register default health checks
        self.register_check('database', self.check_database)
        self.register_check('disk_space', self.check_disk_space)
        self.register_check('memory', self.check_memory)
    
    def register_check(self, name: str, check_func, timeout: int = 30):
        """Register a health check"""
        self.checks[name] = {
            'func': check_func,
            'timeout': timeout
        }
    
    def check_database(self) -> Dict[str, Any]:
        """Check database connectivity"""
        try:
            start_time = time.time()
            
            # Simple connectivity test
            result = db.session.execute(text("SELECT 1"))
            result.fetchone()
            
            duration = time.time() - start_time
            
            return {
                'status': 'healthy',
                'response_time': duration,
                'message': 'Database connection successful'
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Database connection failed'
            }
    
    def check_disk_space(self) -> Dict[str, Any]:
        """Check disk space"""
        try:
            disk = psutil.disk_usage('/')
            percent_used = (disk.used / disk.total) * 100
            
            status = 'healthy'
            if percent_used > 90:
                status = 'critical'
            elif percent_used > 80:
                status = 'warning'
            
            return {
                'status': status,
                'percent_used': percent_used,
                'free_gb': disk.free / (1024**3),
                'total_gb': disk.total / (1024**3),
                'message': f'Disk usage: {percent_used:.1f}%'
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Failed to check disk space'
            }
    
    def check_memory(self) -> Dict[str, Any]:
        """Check memory usage"""
        try:
            memory = psutil.virtual_memory()
            percent_used = memory.percent
            
            status = 'healthy'
            if percent_used > 90:
                status = 'critical'
            elif percent_used > 80:
                status = 'warning'
            
            return {
                'status': status,
                'percent_used': percent_used,
                'available_gb': memory.available / (1024**3),
                'total_gb': memory.total / (1024**3),
                'message': f'Memory usage: {percent_used:.1f}%'
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Failed to check memory'
            }
    
    def run_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {}
        overall_status = 'healthy'
        
        for name, check_config in self.checks.items():
            try:
                # Run check with timeout
                result = check_config['func']()
                results[name] = result
                
                # Determine overall status
                if result['status'] == 'critical':
                    overall_status = 'critical'
                elif result['status'] == 'unhealthy' and overall_status != 'critical':
                    overall_status = 'unhealthy'
                elif result['status'] == 'warning' and overall_status == 'healthy':
                    overall_status = 'warning'
                    
            except Exception as e:
                results[name] = {
                    'status': 'unhealthy',
                    'error': str(e),
                    'message': f'Health check failed: {name}'
                }
                overall_status = 'unhealthy'
        
        return {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': results
        }


class PerformanceMonitor:
    """Performance monitoring middleware"""
    
    def __init__(self, app: Flask = None):
        self.metrics_collector = MetricsCollector()
        self.db_monitor = DatabaseMonitor()
        self.health_checker = HealthChecker()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize performance monitor with Flask app"""
        self.app = app
        
        # Register request hooks
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        
        # Register enhanced health endpoint
        app.add_url_rule('/health/detailed', 'health_detailed', self._detailed_health_check)
    
    def _before_request(self):
        """Record request start time"""
        g.start_time = time.time()
    
    def _after_request(self, response):
        """Record request metrics"""
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            
            # Record request metrics
            self.metrics_collector.record_metric('request_duration', duration, {
                'method': request.method,
                'endpoint': request.endpoint or 'unknown',
                'status_code': response.status_code
            })
            
            # Record response status
            self.metrics_collector.increment_counter('requests', 1, {
                'method': request.method,
                'status_code': response.status_code
            })
            
            # Log slow requests
            if duration > 2.0:  # Log requests taking more than 2 seconds
                logger.warning(
                    f"Slow request detected: {request.method} {request.url}",
                    duration=duration,
                    endpoint=request.endpoint,
                    status_code=response.status_code
                )
        
        return response
    
    def _detailed_health_check(self):
        """Enhanced health check endpoint"""
        from flask import jsonify
        
        health_status = self.health_checker.run_checks()
        metrics_summary = self.metrics_collector.get_metrics_summary()
        db_metrics = self.db_monitor.get_metrics()
        
        response = {
            'status': health_status['status'],
            'timestamp': health_status['timestamp'],
            'version': current_app.config.get('PORTAL_VERSION', 'unknown'),
            'environment': current_app.config.get('ENV', 'unknown'),
            'uptime': metrics_summary.get('system', {}).get('uptime', 0),
            'health_checks': health_status['checks'],
            'metrics': {
                'system': metrics_summary.get('system', {}),
                'database': db_metrics,
                'requests': {
                    'avg_duration': metrics_summary.get('request_duration', {}).get('avg', 0),
                    'total_requests': sum(metrics_summary.get('counters', {}).values())
                }
            }
        }
        
        status_code = 200 if health_status['status'] == 'healthy' else 503
        return jsonify(response), status_code


# Global monitoring instance
monitor = PerformanceMonitor()


def track_performance(operation_name: str):
    """Decorator to track performance of functions"""
    def decorator(f):
        from functools import wraps
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()
            try:
                result = f(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record successful operation
                monitor.metrics_collector.record_metric(f'{operation_name}_duration', duration)
                monitor.metrics_collector.increment_counter(f'{operation_name}_success')
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                
                # Record failed operation
                monitor.metrics_collector.record_metric(f'{operation_name}_duration', duration)
                monitor.metrics_collector.increment_counter(f'{operation_name}_error')
                
                logger.error(f"Operation {operation_name} failed after {duration:.2f}s: {e}")
                raise
        
        return decorated_function
    return decorator


def get_metrics() -> Dict[str, Any]:
    """Get current metrics"""
    return monitor.metrics_collector.get_metrics_summary()


def get_health_status() -> Dict[str, Any]:
    """Get current health status"""
    return monitor.health_checker.run_checks()
