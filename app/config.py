import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'

class Config:
    """Base configuration"""
    
    # Core Security
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY or SECRET_KEY == "default_fallback_key":
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError(
                "SECRET_KEY must be set in environment for production. "
                "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        else:
            # Development fallback
            SECRET_KEY = "dev-secret-key-change-in-production"

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if not SQLALCHEMY_DATABASE_URI:
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError("DATABASE_URL must be set in environment for production")
        else:
            # Development fallback
            SQLALCHEMY_DATABASE_URI = "sqlite:///dev.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File Uploads
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
    ALLOWED_EXTENSIONS = {'xls', 'xlsx', 'csv'}
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(500 * 1024 * 1024)))  # 500MB

    # Data Dump Configuration
    DATADUMP_GENERATED_FOLDER = os.getenv("DATADUMP_GENERATED_FOLDER")
    USER_UPLOADED_FOLDER = os.getenv("USER_UPLOADED_FOLDER")
    DATADUMP_UPLOAD_FOLDER = os.getenv(
        "DATADUMP_UPLOAD_FOLDER",
        os.path.join(BASE_DIR, "app", "static", "uploads", "datadumps")
    )
    DATADUMP_ALLOWED_EXTENSIONS = {'gz', 'dump', 'sql', 'tar', 'zip'}

    # Security & Session
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"  # Default to false for development
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")  # Lax for better compatibility
    SESSION_COOKIE_DOMAIN = None  # Allow cookies to work across all domains (including IP addresses)
    SESSION_COOKIE_PARTITIONED = False  # Disable partitioned cookies for compatibility
    PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", str(60 * 60 * 2)))  # 2 hours

    # CSRF Protection (enabled for security, can be disabled per-route if needed)
    WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "true").lower() == "true"
    WTF_CSRF_TIME_LIMIT = int(os.getenv("WTF_CSRF_TIME_LIMIT", "43200"))  # 12 hours

    # Email Verification
    REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"

    # Vector Search Configuration
    VECTOR_SEARCH_LIMIT = int(os.getenv("VECTOR_SEARCH_LIMIT", "50"))
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))
    SUGGESTION_SIMILARITY_THRESHOLD = float(os.getenv("SUGGESTION_SIMILARITY_THRESHOLD", "0.65"))
    SUGGESTION_MIN_MARGIN = float(os.getenv("SUGGESTION_MIN_MARGIN", "0.02"))

    # Embeddings Configuration
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "")
    EMBEDDING_CACHE_SIZE = int(os.getenv("EMBEDDING_CACHE_SIZE", "5000"))
    EMBEDDING_PRELOAD = os.getenv("EMBEDDING_PRELOAD", "true")
    EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "20"))
    
    # Upload Configuration
    UPLOAD_MAX_ROWS = int(os.getenv("UPLOAD_MAX_ROWS", "1000"))

    # Portal Version
    PORTAL_VERSION = os.getenv("PORTAL_VERSION")

    # MIME Validation
    UPLOAD_ALLOWED_MIME_TYPES = set(os.getenv(
        "UPLOAD_ALLOWED_MIME_TYPES",
        "text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,application/vnd.ms-excel.sheet.macroEnabled.12"
    ).split(","))
    DATADUMP_ALLOWED_MIME_TYPES = set(os.getenv(
        "DATADUMP_ALLOWED_MIME_TYPES",
        "application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ).split(","))

    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200 per day, 50 per hour")

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # Monitoring
    ENABLE_METRICS = os.getenv("ENABLE_METRICS", "false").lower() == "true"
    METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

    # Email Configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "AMS Portal <noreply@ams.local>")
    
    # Notification Settings
    NOTIFICATION_ENABLED = os.getenv("NOTIFICATION_ENABLED", "true").lower() == "true"
    COMMITMENT_REMINDER_DAYS = int(os.getenv("COMMITMENT_REMINDER_DAYS", "7"))

    # Document Management Configuration
    DOCUMENT_ENCRYPTION_KEY = os.getenv("DOCUMENT_ENCRYPTION_KEY")
    if not DOCUMENT_ENCRYPTION_KEY:
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError("DOCUMENT_ENCRYPTION_KEY must be set in environment for document encryption.")
        else:
            # Development fallback
            DOCUMENT_ENCRYPTION_KEY = "dev-encryption-key-32-bytes-long-1234"
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
    TOP_K_CHUNKS = int(os.getenv("TOP_K_CHUNKS", "5"))
    DOCUMENT_SIMILARITY_THRESHOLD = float(os.getenv("DOCUMENT_SIMILARITY_THRESHOLD", "0.72"))
    AUDIT_SALT = os.getenv("AUDIT_SALT")
    if not AUDIT_SALT:
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError("AUDIT_SALT must be set in environment for audit logging.")
        else:
            # Development fallback
            AUDIT_SALT = "dev-audit-salt-32-bytes-long-12345"
    ERASURE_SECRET = os.getenv("ERASURE_SECRET")
    if not ERASURE_SECRET:
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError("ERASURE_SECRET must be set in environment for GDPR compliance.")
        else:
            # Development fallback
            ERASURE_SECRET = "dev-erasure-secret-32-bytes-1234"
    
    # Document allowed MIME types
    DOCUMENT_ALLOWED_MIME_TYPES = set(os.getenv(
        "DOCUMENT_ALLOWED_MIME_TYPES",
        "application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,text/csv"
    ).split(","))

    # Ask Your Database (Natural Language SQL) Configuration
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
    SQL_QUERY_LIMIT = int(os.getenv("SQL_QUERY_LIMIT", "200"))
    SQL_QUERY_TIMEOUT = int(os.getenv("SQL_QUERY_TIMEOUT", "10"))
    READ_ONLY_DB_URI = os.getenv("READ_ONLY_DB_URI")  # Separate read-only database connection for safety
    SQL_QUERY_LOG_FILE = os.getenv("SQL_QUERY_LOG_FILE", "logs/sql_queries.log")

    @staticmethod
    def init_app(app):
        """Initialize app with this configuration"""
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    ENV = "development"
    
    # Development-specific settings
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = "Lax"  # Lax for better compatibility
    # CSRF enabled in development for testing
    
    # More lenient rate limiting for development
    RATELIMIT_DEFAULT = "1000 per day, 200 per hour"
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Development-specific logging
        import logging
        logging.basicConfig(level=logging.DEBUG)


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    ENV = "testing"
    
    # Use in-memory SQLite for testing
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    
    # Disable security features for testing
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    
    # No rate limiting in tests
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_DEFAULT = "10000 per day"


class StagingConfig(Config):
    """Staging configuration"""
    DEBUG = False
    ENV = "staging"
    
    # Staging-specific settings
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_ENABLED = True
    
    # Stricter rate limiting than dev but more lenient than prod
    RATELIMIT_DEFAULT = "500 per day, 100 per hour"
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Staging logging configuration
        import logging
        logging.basicConfig(level=logging.INFO)


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    ENV = "production"
    
    # Production-specific security settings
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Strict"
    WTF_CSRF_ENABLED = True
    
    # Strict rate limiting for production
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    
    # Production should use Redis for rate limiting
    RATELIMIT_STORAGE_URL = os.getenv("REDIS_URL", "memory://")
    
    def __init__(self):
        super().__init__()
        # Remove all fallbacks in production
        if not SECRET_KEY or SECRET_KEY.startswith('dev-'):
            raise ValueError("Production SECRET_KEY must be set and not use development fallback")
            
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Production logging configuration
        import logging
        from logging.handlers import RotatingFileHandler
        
        if not app.debug and not app.testing:
            if not os.path.exists('logs'):
                os.mkdir('logs')
            
            file_handler = RotatingFileHandler(
                'logs/ams.log', 
                maxBytes=10240000,  # 10MB
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            
            app.logger.setLevel(logging.INFO)
            app.logger.info('AMS Production startup')


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig  # Changed to development for better local development
}
