# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do NOT** create public issues for security vulnerabilities
2. Email security details to: ejoanna222@gmail.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)
4. We will respond within 48 hours and provide a timeline for the fix

## Security Features

### Authentication & Authorization

- **Password Hashing**: Argon2id (memory-hard hashing) with configurable parameters
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

1. **Read-Only Role**: Create read-only role for natural language SQL queries
2. **Row-Level Security**: Implement row-level security for multi-tenant data isolation
3. **Connection Pooling**: Use connection pooling with proper timeout settings
4. **Backup Encryption**: Encrypt database backups at rest
5. **Query Limits**: Enforce query timeouts and row limits

### Monitoring

1. **Audit Logs**: Monitor `logs/` directory for security events
2. **Failed Logins**: Alert on repeated failed login attempts
3. **Rate Limit Exceeded**: Monitor for rate limit violations
4. **Database Queries**: Log all natural language SQL queries
5. **File Uploads**: Monitor for suspicious file upload patterns

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

## Recent Security Fixes

### 2026-07-14
- **Dependency Updates**: Updated Pillow (10.2.0 → 12.3.0) and setuptools (70.2.0 → 78.1.1) to fix 11 security vulnerabilities
- **Hardcoded IP Removed**: Removed hardcoded IP address from run.py for security
- **Logging Improvements**: Replaced print() statements with proper logging in enhanced_chatbot.py

### Previous Fixes
- **CSRF Protection**: Re-enabled CSRF globally and added tokens to all forms
- **Authentication**: Added @login_required to natural language SQL endpoint
- **Rate Limiting**: Added rate limiting to login (20/min) and register (5/hour) endpoints
- **SQL Injection**: Wrapped raw SQL with text() function in health check
- **Password Hashing**: Upgraded to Argon2id with backward compatibility for legacy hashes
