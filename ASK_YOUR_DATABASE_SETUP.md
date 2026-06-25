# Ask Your Database - Natural Language SQL Feature

## Overview

This feature allows users to ask questions in plain English and get results from the database using AI-generated SQL queries. It uses a local LLM (Ollama) to convert natural language to PostgreSQL SELECT queries.

## Security Features

**CRITICAL SAFETY MEASURES:**
- All SQL queries are validated using `sqlparse` to ensure they are SELECT-only
- Forbidden keywords (INSERT, UPDATE, DELETE, DROP, ALTER, etc.) are blocked
- Uses a separate read-only PostgreSQL role for query execution
- Applies hard row limits (default: 200 rows) to prevent large result sets
- Sets query timeout (default: 10 seconds) to prevent long-running queries
- Logs all queries for audit trail
- Validates referenced tables against known schema

## Setup Instructions

### 1. Install Dependencies

```bash
pip install sqlparse>=0.4.0
```

Or update requirements.txt:
```
sqlparse>=0.4.0
```

### 2. Install and Configure Ollama

Install Ollama from https://ollama.ai/

Pull a SQL-capable model:
```bash
ollama pull qwen2.5-coder
# or
ollama pull sqlcoder
```

Start Ollama service:
```bash
ollama serve
```

### 3. Create Read-Only PostgreSQL Role

**IMPORTANT:** Run this as a PostgreSQL superuser (e.g., postgres):

```bash
psql -U postgres -d ams_db -f setup_readonly_role.sql
```

This creates a read-only role `ams_readonly` that can only execute SELECT queries.

**Change the password** in the SQL file before running it, or change it after creation:
```sql
ALTER ROLE ams_readonly WITH PASSWORD 'your_secure_password';
```

### 4. Configure Environment Variables

Add these to your `.env` file:

```bash
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder
OLLAMA_TIMEOUT=30

# SQL Query Configuration
SQL_QUERY_LIMIT=200
SQL_QUERY_TIMEOUT=10

# Read-Only Database Connection (CRITICAL - use the read-only role)
READ_ONLY_DB_URI=postgresql://ams_readonly:your_secure_password@localhost:5432/ams_db

# Query Logging
SQL_QUERY_LOG_FILE=logs/sql_queries.log
```

### 5. Restart the Flask Application

```bash
# Stop the current instance and restart
python run.py
```

## Usage

### For Users

1. Navigate to the main dashboard page
2. Scroll down to the "Ask Your Database" section
3. Type a question in plain English (e.g., "how many pending queries?")
4. Press Enter or click "Ask"
5. View the generated SQL (click "View Generated SQL" to see it)
6. Review the results in the table

### Example Questions

- "how many pending queries?"
- "show me all queries from Andhra Pradesh"
- "count queries by state"
- "what are the most recent queries?"
- "how many queries have replies?"

## Architecture

### Components

1. **Frontend (enhanced_index.html + enhanced_scripts.js)**
   - Text input for natural language questions
   - Loading state and error handling
   - Results table display
   - Collapsible SQL code view

2. **Backend API (natural_language_sql.py)**
   - POST /api/ask-db endpoint
   - Validates JSON input
   - Calls service layer

3. **Service Layer (natural_language_sql.py)**
   - Schema introspection from PostgreSQL information_schema
   - Ollama integration for SQL generation
   - SQL validation using sqlparse
   - Query execution with safety limits
   - Audit logging

### Security Validation Flow

1. **Schema Introspection**: Dynamically fetch table/column info from PostgreSQL
2. **SQL Generation**: Send schema + question to Ollama LLM
3. **Keyword Check**: Reject queries with forbidden keywords
4. **Statement Type Check**: Ensure only SELECT statements
5. **Table Validation**: Verify referenced tables exist in schema
6. **Limit Application**: Apply hard row limit if not specified
7. **Timeout Setting**: Set statement_timeout before execution
8. **Read-Only Execution**: Use read-only database role
9. **Audit Logging**: Log all queries for review

## Troubleshooting

### Ollama Connection Issues

If you see "Failed to generate SQL" errors:
- Ensure Ollama is running: `ollama serve`
- Check OLLAMA_HOST in .env matches your Ollama instance
- Verify the model is pulled: `ollama list`
- Test Ollama API: `curl http://localhost:11434/api/generate -d '{"model":"qwen2.5-coder","prompt":"test"}'`

### SQL Validation Errors

If queries are rejected:
- Check the error message for specific validation failure
- Ensure you're asking for data retrieval (SELECT), not modifications
- Review the generated SQL to see what was attempted

### Database Connection Issues

If you see database errors:
- Verify READ_ONLY_DB_URI is correct in .env
- Ensure the read-only role was created successfully
- Test the connection: `psql -U ams_readonly -d ams_db`

### Permission Issues

If you see permission errors:
- Ensure the read-only role has SELECT privileges on all tables
- Re-run the setup_readonly_role.sql script
- Check PostgreSQL logs for specific permission errors

## Audit Trail

All queries are logged to `logs/sql_queries.log` with:
- Timestamp
- Original question
- Generated SQL
- Validation result
- Execution success/failure
- Error messages (if any)

Review this log regularly to ensure queries are appropriate.

## Customization

### Change Ollama Model

Edit `.env`:
```bash
OLLAMA_MODEL=your_preferred_model
```

### Adjust Row Limits

Edit `.env`:
```bash
SQL_QUERY_LIMIT=500  # Increase to 500 rows max
```

### Adjust Query Timeout

Edit `.env`:
```bash
SQL_QUERY_TIMEOUT=15  # Increase to 15 seconds
```

### Change Forbidden Keywords

Edit `app/services/natural_language_sql.py`:
```python
FORBIDDEN_KEYWORDS = {
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER',
    # Add more as needed
}
```

## Important Notes

- **NEVER** skip the SQL validation step - it's a security requirement
- **ALWAYS** use the read-only role for query execution
- **REVIEW** the audit logs regularly
- **KEEP** the read-only role password secure
- **UPDATE** the schema cache if database structure changes (restart app)
- **MONITOR** Ollama resource usage for large deployments

## Performance Considerations

- Schema introspection is cached after first use
- Ollama response time depends on model and hardware
- Query timeout prevents hanging connections
- Row limits prevent large result sets
- Consider rate limiting for production use

## Future Enhancements

Potential improvements:
- Add query history for users
- Support for complex aggregations
- Natural language explanations of results
- Query suggestion/autocomplete
- Export results to CSV/Excel
- Query visualization/charts
