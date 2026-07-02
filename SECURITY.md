# Security Policy

## Security Overview

This document outlines the security measures implemented in the Audit Management System (AMS) and provides guidelines for secure deployment and operation.

## Security Features

### Authentication & Authorization

- **Password Hashing**: Uses Argon2id (memory-hard hashing) with configurable parameters
- **Account Lockout**: Automatic lockout after 5 failed login attempts (15-minute window)
- **Role-Based Access Control (RBAC)**: Four roles (admin, reviewer, modifier, viewer) with granular permissions
- **Session Management**: Secure session cookies with configurable expiration
- **CSRF Protection**: Enabled globally for all state-changing requests

### Input Validation & Sanitization

- **File Upload Validation**: Extension, MIME type, and content signature checks
- **SQL Injection Prevention**: All database queries use parameterized statements or SQLAlchemy ORM
- **XSS Prevention**: HTML sanitization using bleach library
- **Password Strength**: Enforces minimum length, uppercase, lowercase, and digit requirements
- **Document Content Scanning**: Detects instruction injection and exfiltration patterns

### Data Protection

- **Document Encryption**: Fernet encryption for document storage
- **Secure File Handling**: UUID-based filenames with secure_filename()
- **Database Encryption**: PostgreSQL with pgvector for vector embeddings
- **Read-Only Database Role**: Separate read-only role for natural language SQL queries
- **Audit Logging**: Comprehensive logging of security events and data changes

### API Security

- **Rate Limiting**: Configurable rate limits on sensitive endpoints (login, register, chat)
- **Authentication Required**: All API endpoints require authentication except health checks
- **Admin-Only Endpoints**: Protected with @admin_required decorator
- **Secure Headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options configured

## Security Fixes Applied (Current Audit)

### 1. CSRF Protection Re-enabled
- **Issue**: CSRF protection was globally disabled
- **Fix**: Re-enabled CSRF by default in `app/config.py`
- **Impact**: Prevents cross-site request forgery attacks

### 2. Missing Import Fixed
- **Issue**: Missing `re` import in `security_service.py`
- **Fix**: Added `import re` statement
- **Impact**: Ensures input sanitization works correctly

### 3. Unprotected Endpoints Secured
- **Issue**: Natural language SQL endpoint lacked authentication
- **Fix**: Added `@login_required` to `/api/ask-db` endpoint
- **Impact**: Prevents unauthorized database access

### 4. Chat Endpoint Hardened
- **Issue**: Chat endpoint lacked rate limiting
- **Fix**: Added `@login_required` and rate limiting (30/min)
- **Impact**: Prevents abuse and DoS attacks

### 5. SQL Injection Risk Fixed
- **Issue**: Raw SQL without text() wrapper in health check
- **Fix**: Wrapped SQL with `text()` function
- **Impact**: Prevents SQL injection via raw queries

### 6. Debug Logging Removed
- **Issue**: Multiple `print()` statements in production code
- **Fix**: Replaced with proper `logging` module
- **Impact**: Better security and production readiness

### 7. Auth Endpoints Rate Limited
- **Issue**: Login and registration endpoints lacked rate limiting
- **Fix**: Added rate limiting (login: 20/min, register: 5/hour)
- **Impact**: Prevents brute force attacks

## Security Best Practices

### Deployment

1. **Environment Variables**: Never commit secrets to git. Use `.env` file (gitignored)
2. **Production Secrets**: Generate strong random secrets for:
   - `SECRET_KEY`: Use `python -c 'import secrets; print(secrets.token_hex(32))'`
   - `DOCUMENT_ENCRYPTION_KEY`: Use Fernet key generation
   - `AUDIT_SALT`: Use cryptographically secure random salt
3. **Database**: Use PostgreSQL in production with proper SSL/TLS
4. **HTTPS**: Always use HTTPS in production with valid certificates
5. **Firewall**: Restrict database access to application servers only

### Configuration

1. **Debug Mode**: Set `FLASK_DEBUG=false` in production
2. **Session Cookies**: Enable `SESSION_COOKIE_SECURE` and `SESSION_COOKIE_HTTPONLY`
3. **CSRF**: Keep `WTF_CSRF_ENABLED=true` (default)
4. **Rate Limiting**: Configure Redis for distributed rate limiting
5. **Logging**: Use structured logging with log rotation

### Database Security

1. **Read-Only Role**: Run `setup_readonly_role.sql` to create read-only role for natural language SQL
2. **Row-Level Security**: Implement row-level security for multi-tenant data isolation
3. **Connection Pooling**: Use connection pooling with proper timeout settings
4. **Backup Encryption**: Encrypt database backups at rest
5. **Query Limits**: Enforce query timeouts and row limits (already implemented)

### Monitoring

1. **Audit Logs**: Monitor `logs/` directory for security events
2. **Failed Logins**: Alert on repeated failed login attempts
3. **Rate Limit Exceeded**: Monitor for rate limit violations
4. **Database Queries**: Log all natural language SQL queries
5. **File Uploads**: Monitor for suspicious file upload patterns

## Vulnerability Reporting

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** create public issues for security vulnerabilities
2. Email security details to: [ejoanna222@gmail.com]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)
4. We will respond within 48 hours and provide a timeline for the fix

## Security Checklist

### Before Production Deployment

- [ ] All placeholder passwords changed (`CHANGE_THIS_PASSWORD`)
- [ ] Strong `SECRET_KEY` generated and set
- [ ] `DOCUMENT_ENCRYPTION_KEY` generated and set
- [ ] `FLASK_DEBUG=false`
- [ ] `SESSION_COOKIE_SECURE=true`
- [ ] `WTF_CSRF_ENABLED=true`
- [ ] Database SSL/TLS enabled
- [ ] Read-only database role created
- [ ] HTTPS configured with valid certificate
- [ ] Firewall rules configured
- [ ] Log rotation configured
- [ ] Backup strategy in place
- [ ] Monitoring/alerting configured

### Ongoing Security

- [ ] Regular dependency updates (`pip-audit`, `safety`)
- [ ] Review audit logs weekly
- [ ] Monitor failed login attempts
- [ ] Test backup restoration quarterly
- [ ] Security audit annually
- [ ] Update documentation after security changes

## Dependencies

Security-critical dependencies:
- `argon2-cffi==23.1.0` - Password hashing
- `cryptography==41.0.7` - Encryption
- `bleach==6.1.0` - HTML sanitization
- `Flask-WTF==1.2.1` - CSRF protection
- `Flask-Limiter==3.5.0` - Rate limiting

Run `pip-audit` regularly to check for known vulnerabilities:
```bash
pip install pip-audit
pip-audit
```
