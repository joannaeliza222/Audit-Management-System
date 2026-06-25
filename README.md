# Audit Management System (AMS)

A comprehensive, production-ready audit management system with advanced AI-powered query intelligence, commitment tracking, and complete local operation capabilities.

## Features

### Core Functionality
- **Intelligent Query Processing** with AI-powered categorization and response suggestions
- **Commitment Tracking System** for monitoring promises made in responses
- **Version History & Change Tracking** with complete audit trails
- **Document Processing Pipeline** supporting PDF, Excel, and CSV with Q&A extraction
- **Advanced Analytics Dashboard** with comprehensive reporting and insights
- **Role-based FAQ workflow** with Replied, Pending, and Review pages
- **Advanced search** with vector similarity matching
- **Bulk operations** for efficient content management
- **Data dump management** with secure file handling

### AI/NLP Capabilities (100% Local)
- **Local Sentence Transformers** for semantic search and embeddings
- **Query Intent Analysis** with automatic categorization
- **Response Suggestion Engine** based on historical data
- **Commitment Detection** using pattern recognition
- **Similar Query Matching** with confidence scoring

### Document Intelligence
- **PDF Text Extraction** with Q&A pair identification
- **Excel/CSV Processing** with structured data parsing
- **Automatic Commitment Extraction** from uploaded documents
- **Content Validation** with confidence scoring
- **Batch Processing** for large document volumes

### Security Features
- **Authentication & Authorization** with role-based permissions
- **CSRF Protection** with configurable timeouts
- **Secure Headers** (CSP, HSTS, X-Frame-Options, etc.)
- **Input Sanitization** preventing XSS and SQL injection
- **Rate Limiting** with Redis backend and configurable limits
- **File Upload Validation** with type and content verification
- **Audit Logging** for security events and data changes
- **Session Management** with secure cookie settings
- **Account Lockout** after failed login attempts

### Production Features
- **Environment-based configuration** (Development, Staging, Production)
- **Structured logging** with JSON formatting and log rotation
- **Centralized error handling** with custom exception classes
- **Input validation and sanitization** against XSS and injection attacks
- **Advanced rate limiting** with Redis backend support
- **Comprehensive monitoring** with health checks and metrics
- **Security hardening** with CSRF protection, secure headers, and CORS
- **Responsive design** optimized for mobile, tablet, and desktop

## Local Operation Guarantee

This system operates **100% locally** with:
- **No external API calls** - All AI processing uses local models
- **No cloud dependencies** - Complete on-premise operation
- **No data transmission** - All data remains within your infrastructure
- **Air-gapped capability** - Can operate in isolated networks
- **Local AI models** - Sentence Transformers and pattern recognition

## Tech Stack

### Backend
- **Python 3.8+**
- **Flask 2.3+** - Web framework
- **SQLAlchemy** - ORM
- **PostgreSQL 12+** with pgvector extension - Database
- **Redis 6+** - Rate limiting (production)

### AI/ML
- **Sentence Transformers** (MiniLM-L6-v2) - Local embeddings
- **PyTorch** - ML framework
- **pgvector** - Vector similarity search

### Frontend
- **Bootstrap 5** - UI framework
- **jQuery** - JavaScript library
- **Poppins Font** - Typography

### Security
- **Argon2** - Password hashing
- **Bleach** - HTML sanitization
- **Marshmallow** - Input validation
- **Flask-Limiter** - Rate limiting

## System Requirements

- **Python 3.8+**
- **PostgreSQL 12+** with pgvector extension
- **Redis 6+** (for production rate limiting)
- **8GB+ RAM** (recommended for AI processing)
- **PyTorch** (for local AI models)

## Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd ams
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit with your configuration
nano .env
```

**Required Environment Variables:**
```bash
# Core Configuration
FLASK_ENV=production
SECRET_KEY=your-secret-key-here  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/ams_db

# Redis (Production)
REDIS_URL=redis://localhost:6379/0

# File Uploads
UPLOAD_FOLDER=/var/lib/ams/uploads
DATADUMP_UPLOAD_FOLDER=/var/lib/ams/datadump/uploads
DATADUMP_GENERATED_FOLDER=/var/lib/ams/datadump/generated
USER_UPLOADED_FOLDER=/var/lib/ams/user/uploads
MAX_CONTENT_LENGTH=64424509400  # 60GB

# Security
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Strict
WTF_CSRF_ENABLED=true

# CORS (comma-separated list, NOT wildcard in production)
CORS_ORIGINS=https://yourdomain.com

# Document Security (REQUIRED in production)
DOCUMENT_ENCRYPTION_KEY=your-encryption-key  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
AUDIT_SALT=your-audit-salt  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
ERASURE_SECRET=your-erasure-secret  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'

# Optional: Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=AMS Portal <noreply@yourdomain.com>

# Optional: Ollama for Natural Language SQL
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder
READ_ONLY_DB_URI=postgresql://ams_readonly:password@localhost:5432/ams_db

# Monitoring (Optional)
ENABLE_METRICS=true
METRICS_PORT=9090
```

### 5. Database Setup
```bash
# Initialize database
flask db upgrade

# Create initial user (optional)
python scripts/init_db.py
```

## Usage

### Development
```bash
python run.py
```

### Production
```bash
# Start with Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app

# Or use production starter
python scripts/start_production.py
```

### Docker
```bash
# Build and run with Docker Compose
docker-compose up --build
```

## Project Structure

```
ams/
├── app/                      # Main application package
│   ├── __init__.py          # Application factory
│   ├── config.py            # Environment configurations
│   ├── models.py            # Core database models
│   ├── audit_models.py      # Audit-specific models
│   ├── document_models.py   # Document processing models
│   ├── api/                 # API routes
│   │   └── routes/         # Route handlers
│   ├── services/            # Business logic services
│   ├── utils/              # Utility functions
│   ├── static/             # CSS, JS, images
│   └── templates/          # HTML templates
├── scripts/                # Build and deployment scripts
├── migrations/             # Database migrations
├── data/                   # AI configuration and patterns
├── tests/                  # Test suite
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
└── README.md              # This file
```

## API Documentation

### Authentication Endpoints
- `POST /auth/login` - User login
- `POST /auth/logout` - User logout

### FAQ Endpoints
- `GET /api/faq/search` - Search FAQs
- `POST /api/faq` - Create FAQ
- `PUT /api/faq/<id>` - Update FAQ
- `DELETE /api/faq/<id>` - Delete FAQ

### Health Endpoints
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed system status

## Configuration

### Environment Modes
- **Development**: Debug enabled, relaxed security, verbose logging
- **Staging**: Production-like environment with testing features
- **Production**: Full security, optimized performance, structured logging

### Rate Limiting
```python
# Default limits (configurable)
DEFAULT_LIMIT = "200 per day, 50 per hour"
AUTH_LIMIT = "5 per minute, 20 per hour"
SEARCH_LIMIT = "30 per minute, 200 per hour"
UPLOAD_LIMIT = "10 per minute, 50 per hour"
```

## Security Considerations

### Authentication
- **Password Hashing**: Argon2 with configurable parameters
- **Session Management**: Secure cookies with proper attributes
- **Rate Limiting**: Prevents brute force attacks
- **CSRF Protection**: Enabled for all state-changing requests

### Input Validation
- **XSS Prevention**: HTML sanitization and output encoding
- **SQL Injection**: Parameterized queries and ORM usage
- **File Upload**: Type validation, size limits, and content verification

### Infrastructure Security
- **HTTPS Required**: Production enforces SSL/TLS
- **Secure Headers**: Comprehensive header configuration
- **CORS Restrictions**: Configurable origin allowlist
- **Environment Variables**: No hardcoded secrets

## Troubleshooting

### Application Won't Start
```bash
# Check environment variables
python -c "import os; print('SECRET_KEY:', os.getenv('SECRET_KEY'))"

# Check database connection
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.session.execute(db.text('SELECT 1'))"
```

### Database Issues
```bash
# Check migrations
flask db current

# Reset database (development only)
flask db downgrade base
flask db upgrade
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- **Documentation**: Check this README and inline code comments
- **Issues**: Create an issue in the repository
- **Security**: Report security issues privately

---

**Version**: 1.0.0  
**Status**: Production Ready ✅
