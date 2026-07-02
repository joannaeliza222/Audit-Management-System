#!/usr/bin/env python3
"""
Production startup script for AMS
"""
import os
import sys
import signal
import time
from pathlib import Path
from multiprocessing import Process


def run_gunicorn():
    """Run application with Gunicorn"""
    import subprocess
    
    gunicorn_cmd = [
        'gunicorn',
        '--bind', os.getenv('GUNICORN_BIND', '0.0.0.0:5000'),
        '--workers', '4',
        '--worker-class', 'sync',
        '--timeout', '120',
        '--keepalive', '5',
        '--max-requests', '1000',
        '--max-requests-jitter', '100',
        '--access-logfile', '-',
        '--error-logfile', '-',
        '--log-level', 'info',
        'run:app'
    ]
    
    try:
        subprocess.run(gunicorn_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Gunicorn failed: {e}")
        sys.exit(1)


def run_celery_worker():
    """Run Celery worker for background tasks"""
    try:
        from celery import Celery
        
        # Configure Celery
        celery = Celery('ams')
        # Note: celeryconfig.py is optional - skip if not configured
        try:
            celery.config_from_object('celeryconfig')
        except ImportError:
            print("celeryconfig.py not found, using default configuration")
            celery.conf.update(
                broker_url=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
                result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
            )
        
        # Start worker
        celery.worker_main([
            'worker',
            '--loglevel=info',
            '--concurrency=4',
            '--prefetch-multiplier=1',
            '--max-tasks-per-child=1000'
        ])
    except ImportError:
        print("Celery not available, skipping worker")
    except Exception as e:
        print(f"Celery worker failed: {e}")


def run_celery_beat():
    """Run Celery beat for scheduled tasks"""
    try:
        from celery import Celery
        
        # Configure Celery
        celery = Celery('ams')
        # Note: celeryconfig.py is optional - skip if not configured
        try:
            celery.config_from_object('celeryconfig')
        except ImportError:
            print("celeryconfig.py not found, using default configuration")
            celery.conf.update(
                broker_url=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
                result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
            )
        
        # Start beat scheduler
        celery.worker_main([
            'beat',
            '--loglevel=info',
            '--pidfile=/tmp/celerybeat.pid'
        ])
    except ImportError:
        print("Celery not available, skipping beat")
    except Exception as e:
        print(f"Celery beat failed: {e}")


def check_environment():
    """Check production environment"""
    print("Checking production environment...")
    
    # Check required environment variables
    required_vars = ['SECRET_KEY', 'DATABASE_URL']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"✗ Missing environment variables: {', '.join(missing_vars)}")
        return False
    
    # Check Flask environment
    if os.getenv('FLASK_ENV') == 'production':
        print("⚠ FLASK_ENV is deprecated, use FLASK_DEBUG=False instead")
    if os.getenv('FLASK_DEBUG', 'false').lower() == 'true':
        print("⚠ FLASK_DEBUG is True in production - set to False")
    
    # Check database connectivity
    try:
        from app import create_app, db
        from sqlalchemy import text
        app = create_app()
        
        with app.app_context():
            db.session.execute(text("SELECT 1"))
            print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    # Check Redis connectivity (if configured)
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        try:
            import redis
            r = redis.from_url(redis_url)
            r.ping()
            print("✓ Redis connection successful")
        except Exception as e:
            print(f"⚠ Redis connection failed: {e}")
    
    print("✓ Environment check completed")
    return True


def setup_logging():
    """Setup production logging"""
    import logging
    from logging.handlers import RotatingFileHandler
    
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        handlers=[
            RotatingFileHandler('logs/ams.log', maxBytes=10*1024*1024, backupCount=10),
            logging.StreamHandler()
        ]
    )
    
    # Suppress noisy loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def handle_signals():
    """Handle shutdown signals gracefully"""
    def signal_handler(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def main():
    """Main production startup function"""
    print("Starting AMS in production mode...")
    
    # Handle signals
    handle_signals()
    
    # Setup logging
    setup_logging()
    
    # Check environment
    if not check_environment():
        sys.exit(1)
    
    # Change to project directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Start processes
    processes = []
    
    try:
        # Start Gunicorn
        if '--no-gunicorn' not in sys.argv:
            gunicorn_process = Process(target=run_gunicorn)
            gunicorn_process.start()
            processes.append(gunicorn_process)
            print("✓ Gunicorn started")
        
        # Start Celery worker (if available)
        if '--no-celery' not in sys.argv:
            celery_worker_process = Process(target=run_celery_worker)
            celery_worker_process.start()
            processes.append(celery_worker_process)
            print("✓ Celery worker started")
        
        # Start Celery beat (if available)
        if '--no-beat' not in sys.argv:
            celery_beat_process = Process(target=run_celery_beat)
            celery_beat_process.start()
            processes.append(celery_beat_process)
            print("✓ Celery beat started")
        
        print("All processes started successfully")
        print("Press Ctrl+C to stop")
        
        # Wait for processes
        while True:
            time.sleep(1)
            
            # Check if any process died
            for process in processes:
                if not process.is_alive():
                    print(f"Process {process.name} died unexpectedly")
                    sys.exit(1)
    
    except KeyboardInterrupt:
        print("\nShutting down...")
        
        # Terminate all processes
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
                
                if process.is_alive():
                    print(f"Force killing process {process.name}")
                    process.kill()
                    process.join()
        
        print("Shutdown complete")


if __name__ == '__main__':
    main()
