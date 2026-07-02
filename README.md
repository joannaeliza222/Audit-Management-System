# Audit Management System (AMS)

A comprehensive audit management system with AI-powered query intelligence, commitment tracking, and document processing capabilities. The system operates 100% locally with no external API dependencies.

## Features

- **Query Management**: Create, track, and manage audit queries with AI-powered categorization
- **Commitment Tracking**: Monitor and track commitments made in responses with automatic detection
- **Document Processing**: Upload and process PDF, DOCX, and text documents with Q&A extraction
- **Semantic Search**: Vector-based similarity search using local Sentence Transformers
- **Role-Based Access**: Admin, reviewer, modifier, and viewer roles with appropriate permissions
- **Analytics Dashboard**: Comprehensive reporting and insights on queries and commitments
- **Natural Language SQL**: Query the database using plain English (optional, requires Ollama)
- **Data Dump Management**: Secure handling of data dump requests and file sharing

## Tech Stack

- **Backend**: Python 3.8+, Flask 2.3+, SQLAlchemy
- **Database**: PostgreSQL 12+ with pgvector extension
- **AI/ML**: Local Sentence Transformers (MiniLM-L6-v2), PyTorch
- **Frontend**: Bootstrap 5, jQuery
- **Security**: Argon2 password hashing, Bleach sanitization, Flask-Limiter

## System Requirements

- Python 3.8+
- PostgreSQL 12+ with pgvector extension
- Redis 6+ (optional, for production rate limiting)
- 8GB+ RAM (recommended for AI processing)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd AMS
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

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your configuration. Required variables:

```bash
# Core Configuration
FLASK_ENV=production
SECRET_KEY=your-secret-key-here  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/ams_db

# Security
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Strict
WTF_CSRF_ENABLED=true

# Document Security (REQUIRED in production)
DOCUMENT_ENCRYPTION_KEY=your-encryption-key  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
AUDIT_SALT=your-audit-salt  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'
ERASURE_SECRET=your-erasure-secret  # Generate with: python -c 'import secrets; print(secrets.token_hex(32))'

# File Uploads
UPLOAD_FOLDER=/path/to/uploads
MAX_CONTENT_LENGTH=64424509400  # 60GB

# CORS (comma-separated list, use * only for development)
CORS_ORIGINS=https://yourdomain.com

# Initial Admin User
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_NAME=Administrator
INITIAL_ADMIN_STATE=Default
INITIAL_ADMIN_PASSWORD=secure-password-here
```

### 5. Database Setup

```bash
# Run migrations
flask db upgrade

# Create initial admin user
python scripts/init_db.py
```

### 6. Optional: Natural Language SQL Setup

If you want to use the "Ask Your Database" feature:

1. Install Ollama from https://ollama.ai/
2. Pull a model: `ollama pull qwen2.5-coder`
3. Start Ollama: `ollama serve`
4. Set up read-only database role:
   ```bash
   psql -U postgres -d ams_db -f setup_readonly_role.sql
   ```
5. Update `.env` with Ollama configuration (see `.env.example`)

## Usage

### Development

```bash
python run.py
```

### Production

```bash
# Using Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app

# Or use the production starter script
python scripts/start_production.py
```

## Project Structure

```
AMS/
├── app/
│   ├── __init__.py          # Application factory
│   ├── config.py            # Environment configurations
│   ├── models.py            # Core database models (User, FAQ, DraftFAQ, etc.)
│   ├── audit_models.py      # Audit-specific models (AuditQuery, Commitment)
│   ├── document_qa_models.py # Document Q&A models (SecureDocument, QADocumentChunk)
│   ├── api/
│   │   └── routes/         # API route handlers
│   ├── services/            # Business logic (AI, vector store, document processing)
│   ├── utils/              # Utility functions (validation, logging, security)
│   ├── static/             # CSS, JS, images
│   └── templates/          # HTML templates
├── scripts/                # Utility scripts (init_db, start_production)
├── migrations/             # Database migrations
├── data/                   # AI configuration and patterns
├── tests/                  # Test suite
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variable template
├── .gitignore             # Git ignore rules
└── README.md              # This file
```

## Configuration

### Environment Modes

- **Development**: Debug enabled, relaxed security, verbose logging
- **Testing**: In-memory SQLite, disabled security features
- **Staging**: Production-like with testing features
- **Production**: Full security, optimized performance, structured logging

Set via `FLASK_ENV` environment variable.

### Rate Limiting

Default limits (configurable via environment variables):
- General: 200 per day, 50 per hour
- Authentication: 5 per minute, 20 per hour
- Search: 30 per minute, 200 per hour
- Upload: 10 per minute, 50 per hour

## Security Features

- **Authentication**: Role-based access control (admin, reviewer, modifier, viewer)
- **Password Hashing**: Argon2 with configurable parameters
- **Session Management**: Secure cookies with HttpOnly, Secure, and SameSite attributes
- **CSRF Protection**: Enabled for state-changing requests
- **Rate Limiting**: Configurable limits with Redis backend support
- **Input Validation**: HTML sanitization (Bleach) and SQL injection prevention
- **File Upload Validation**: MIME type checking, size limits, and content verification
- **Secure Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- **Account Lockout**: After 5 failed login attempts within 15 minutes
- **Audit Logging**: All actions logged for compliance

## API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/logout` - User logout
- `POST /auth/register` - User registration

### Query Management
- `GET /` - Main dashboard
- `GET /pending` - Pending queries
- `GET /replied` - Replied queries
- `GET /review_drafts` - Review draft responses
- `POST /api/pending_questions` - Get pending questions
- `POST /api/save_pending` - Save draft response
- `POST /api/merge_draft` - Merge draft to FAQ

### Document Q&A
- `GET /document-qa` - Document Q&A interface
- `POST /api/documents/upload` - Upload document
- `GET /api/documents` - List documents
- `POST /api/documents/<id>/query` - Query document

### Analytics
- `GET /analytics` - Analytics dashboard
- `GET /commitment-dashboard` - Commitment tracking
- `GET /api/analytics/performance` - Performance metrics

### Health
- `GET /health` - Basic health check

## Troubleshooting

### Database Connection Issues

```bash
# Test database connection
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.session.execute(db.text('SELECT 1'))"
```

### Migration Issues

```bash
# Check current migration version
flask db current

# Reset database (development only)
flask db downgrade base
flask db upgrade
```

### AI Model Issues

If the embedding model fails to load:
- Ensure PyTorch is installed correctly
- Check available RAM (minimum 8GB recommended)
- Set `EMBEDDING_PRELOAD=false` in `.env` to disable preloading

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request


## Support

For support and questions:
- **Documentation**: Check this README and inline code comments
- **Issues**: Create an issue in the repository
- **Security**: Report security issues privately


