import os
import uuid
from flask import Flask, render_template, jsonify, g, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from .config import config
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_login import LoginManager
from datetime import datetime, timedelta
from werkzeug.exceptions import HTTPException

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
mail = Mail()
login_manager = LoginManager()

def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')
    
    app = Flask(__name__, template_folder="templates", static_folder="static")
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    # Set session timeout
    app.permanent_session_lifetime = timedelta(seconds=app.config.get('PERMANENT_SESSION_LIFETIME', 28800))
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app)
    
    # Initialize Flask-Mail
    mail.init_app(app)
    
    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # Initialize CSRF protection
    if app.config.get('WTF_CSRF_ENABLED', False):
        csrf.init_app(app)

    # Initialize CORS
    cors_origins = app.config.get('CORS_ORIGINS', ['*'])
    if cors_origins == ['*'] and app.config.get('ENV') == 'production':
        app.logger.warning("CORS_ORIGINS is set to wildcard '*' in production. This is not recommended.")
    CORS(app, origins=cors_origins)

    # Initialize rate limiting
    try:
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[app.config.get('RATELIMIT_DEFAULT', '200 per day, 50 per hour')],
            storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
        )
        app.limiter = limiter
    except Exception as e:
        app.logger.warning(f"Rate limiting disabled due to: {e}")
        app.limiter = None
    
    # Setup structured logging
    try:
        from app.utils.logging_config import setup_logging, log_request_info, log_response_info
        setup_logging(app)
    except ImportError:
        # Fallback to basic logging if utils not available yet
        import logging
        logging.basicConfig(level=logging.INFO)
        app.logger.info("Basic logging configured (utils not available)")
    
    # Request tracking
    @app.before_request
    def before_request():
        g.request_id = str(uuid.uuid4())
        if hasattr(request, 'remote_addr'):
            g.ip_address = request.remote_addr
        try:
            log_request_info()
        except NameError:
            pass  # log_request_info not available
    
    @app.after_request
    def after_request(response):
        try:
            log_response_info(response)
        except NameError:
            pass  # log_response_info not available
        return response
    
    
    # Register enhanced frontend blueprint first (to handle root route)
    try:
        from app.api.routes.enhanced_frontend import enhanced_frontend_bp
        app.register_blueprint(enhanced_frontend_bp)
    except ImportError as e:
        app.logger.warning(f"Enhanced frontend blueprint not available: {e}")
        # Fallback: register auth blueprint first if enhanced frontend is not available
    
    # Login & registration
    from app.api.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.api.routes.replied import replied_bp
    app.register_blueprint(replied_bp)

    from app.api.routes.pending import pending_bp
    app.register_blueprint(pending_bp)

    from app.api.routes.review import review_bp
    app.register_blueprint(review_bp)

    from app.api.routes.datadump import dump_bp
    app.register_blueprint(dump_bp)

    from app.api.routes.futurefix import futurefix_bp
    app.register_blueprint(futurefix_bp)
    
    # Register commitment dashboard blueprint
    from app.api.routes.commitment_dashboard import commitment_dashboard_bp
    app.register_blueprint(commitment_dashboard_bp)
    
    # Register new audit query management blueprint
    from app.api.routes.audit_queries import audit_bp
    app.register_blueprint(audit_bp, url_prefix='/api/audit')
    
    # Register enhanced query management blueprint
    from app.api.routes.enhanced_query_management import enhanced_query_bp
    app.register_blueprint(enhanced_query_bp, url_prefix='/api/enhanced')
    
    # Register enhanced chatbot blueprint
    from app.api.routes.enhanced_chatbot import enhanced_chatbot_bp
    app.register_blueprint(enhanced_chatbot_bp, url_prefix='/api/chatbot')
    
    # Register chatbot pages blueprint
    from app.api.routes.chatbot_pages import chatbot_pages_bp
    app.register_blueprint(chatbot_pages_bp)
    
    # Register audit analytics blueprint
    from app.api.routes.audit_analytics import audit_analytics_bp
    app.register_blueprint(audit_analytics_bp)
    
    # Register version fixes blueprint
    from app.api.routes.version_fixes import version_fixes_bp
    app.register_blueprint(version_fixes_bp)
    
    # Register future issues blueprint
    from app.api.routes.future_issues import future_issues_bp
    app.register_blueprint(future_issues_bp)
    
    # Register documents management blueprint
    from app.api.routes.documents import documents_bp
    app.register_blueprint(documents_bp)
    
    # Register natural language SQL blueprint
    from app.api.routes.natural_language_sql import natural_language_sql_bp
    app.register_blueprint(natural_language_sql_bp)
    
    # Register document Q&A blueprints
    from app.api.routes.document_qa import document_qa_bp
    app.register_blueprint(document_qa_bp)
    
    from app.api.routes.document_qa_pages import document_qa_pages_bp
    app.register_blueprint(document_qa_pages_bp)
    
    # Setup Flask-Login user loader
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))
    

    # Health check endpoint
    @app.route('/health')
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception:
            db_status = "disconnected"

        return jsonify({
            "status": "healthy",
            "database": db_status,
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    
    # Pre-load embedding model in background (optional)
    if app.config.get('EMBEDDING_PRELOAD', 'true').lower() != 'false':
        try:
            from app.utils.embeddings import _load_embedding_model
            _load_embedding_model()
        except Exception as e:
            # Avoid leaking internal exception details in logs by default.
            app.logger.warning("Failed to pre-load embedding model: " + str(e))
        except ImportError:
            app.logger.warning("Embedding model not available")
    else:
        app.logger.info("Embedding model pre-loading disabled for faster startup")

    @app.after_request
    def set_security_headers(resp):
        # Enhanced security headers
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=()")
        resp.headers.setdefault("X-XSS-Protection", "1; mode=block")
        
        # Content Security Policy
        if app.config.get('ENV') == 'production':
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.plot.ly; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https://huggingface.co https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
            resp.headers.setdefault("Content-Security-Policy", csp)
        else:
            # More permissive CSP for development
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.plot.ly; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https://huggingface.co https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
            resp.headers.setdefault("Content-Security-Policy", csp)
        
        # HSTS in production
        if app.config.get('ENV') == 'production' and request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        
        return resp

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        # Log full stack trace for diagnostics
        try:
            app.logger.exception("Unhandled application error", exc_info=err)
        except Exception:
            pass
        # Roll back any failed transaction.
        try:
            db.session.rollback()
        except Exception:
            pass

        # Preserve normal HTTP errors (404/403/etc)
        if isinstance(err, HTTPException):
            return err

        # In production: generic response. In debug: Flask will show details anyway.
        if app.config.get("DEBUG"):
            raise err
        return jsonify({"error": "Internal server error"}), 500
    
    # Register centralized error handlers
    try:
        from app.utils.error_handlers import register_error_handlers
        register_error_handlers(app)
    except ImportError:
        app.logger.warning("Error handlers not available")
    
    return app




