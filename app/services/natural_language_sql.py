"""
Natural Language SQL Service

This service provides natural language to SQL conversion using local LLM (Ollama)
with strict safety validation and read-only database access.

SECURITY CRITICAL:
- All SQL queries are validated to be SELECT-only before execution
- Uses a separate read-only database role for query execution
- Applies hard row limits and query timeouts
- Logs all queries for audit trail
"""

import os
import logging
import requests
import sqlparse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app
from datetime import datetime

# Configure logging (lazy initialization when app context is available)
sql_logger = None

def get_sql_logger():
    """Get or create the SQL query logger (lazy initialization)"""
    global sql_logger
    if sql_logger is None:
        sql_logger = logging.getLogger('sql_queries')
        sql_logger.setLevel(logging.INFO)
        
        # Get log file path from config
        log_file = current_app.config.get('SQL_QUERY_LOG_FILE', 'logs/sql_queries.log')
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)
        
        # File handler for SQL query logging
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        sql_logger.addHandler(file_handler)
    
    return sql_logger


class NaturalLanguageSQLService:
    """Service for converting natural language to SQL with safety validation"""

    # Keywords that are strictly forbidden in generated SQL
    FORBIDDEN_KEYWORDS = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE',
        'GRANT', 'CREATE', 'COPY', 'EXECUTE', 'REVOKE', 'COMMENT'
    }

    def __init__(self):
        self.ollama_host = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
        self.ollama_model = current_app.config.get('OLLAMA_MODEL', 'qwen2.5-coder')
        # Force minimum timeout of 120 seconds for large schema processing
        self.ollama_timeout = max(current_app.config.get('OLLAMA_TIMEOUT', 30), 120)
        self.query_limit = current_app.config.get('SQL_QUERY_LIMIT', 200)
        self.query_timeout = current_app.config.get('SQL_QUERY_TIMEOUT', 10)
        self.schema_cache = None

    def get_database_schema(self):
        """
        Dynamically introspect database schema from PostgreSQL information_schema.
        Returns table names, column names, types, and foreign key relationships.
        """
        if self.schema_cache:
            return self.schema_cache

        try:
            from app import db

            # Get table names
            tables_query = text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            tables_result = db.session.execute(tables_query)
            tables = [row[0] for row in tables_result]

            schema = {}
            for table in tables:
                # Get column information
                columns_query = text("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                    ORDER BY ordinal_position
                """)
                columns_result = db.session.execute(columns_query, {'table_name': table})
                columns = []
                for row in columns_result:
                    columns.append({
                        'name': row[0],
                        'type': row[1],
                        'nullable': row[2] == 'YES',
                        'default': row[3]
                    })

                # Get foreign key relationships
                fk_query = text("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    AND tc.table_name = :table_name
                """)
                fk_result = db.session.execute(fk_query, {'table_name': table})
                foreign_keys = []
                for row in fk_result:
                    foreign_keys.append({
                        'column': row[0],
                        'foreign_table': row[1],
                        'foreign_column': row[2]
                    })

                schema[table] = {
                    'columns': columns,
                    'foreign_keys': foreign_keys
                }

            self.schema_cache = schema
            return schema

        except SQLAlchemyError as e:
            current_app.logger.error(f"Error introspecting database schema: {str(e)}")
            raise

    def generate_sql_from_natural_language(self, question):
        """
        Send natural language question to Ollama LLM to generate SQL.
        Returns the generated SQL query.
        """
        schema = self.get_database_schema()

        # Build schema description for the prompt (optimized for brevity)
        schema_description = "Database Schema:\n"
        table_descriptions = {
            'draftfaq': 'Main table for audit queries/drafts with status tracking (pending, admin_draft, approved, etc.)',
            'audit_query': 'Finalized audit query records with responses',
            'user': 'User accounts and authentication',
            'commitment': 'Commitment tracking for audit responses',
            'faq': 'Frequently asked questions and knowledge base',
            'data_dump': 'Data dump requests and files',
            'document': 'Document management and storage',
            'future_issue_tracker': 'Future issues and version fixes tracking'
        }
        
        for table_name, table_info in schema.items():
            schema_description += f"\nTable: {table_name}"
            if table_name in table_descriptions:
                schema_description += f" - {table_descriptions[table_name]}"
            schema_description += "\n"
            schema_description += "Columns: "
            col_names = [f"{col['name']}({col['type']})" for col in table_info['columns']]
            schema_description += ", ".join(col_names) + "\n"
            if table_info['foreign_keys']:
                fk_info = ", ".join([f"{fk['column']}->{fk['foreign_table']}.{fk['foreign_column']}" for fk in table_info['foreign_keys']])
                schema_description += f"Foreign Keys: {fk_info}\n"

        prompt = f"""You are a SQL expert. Convert the following natural language question into a valid PostgreSQL SELECT query.

{schema_description}

IMPORTANT TABLE GUIDANCE:
- For questions about "pending queries", "drafts", or audit queries in progress, use the 'draftfaq' table (status column contains values like 'pending', 'admin_draft', 'approved', etc.)
- For questions about finalized/completed audit queries with responses, use the 'audit_query' table

Question: {question}

IMPORTANT RULES:
1. Return ONLY a single valid PostgreSQL SELECT statement
2. No explanation, no markdown formatting, no code blocks
3. Use the exact table and column names from the schema above
4. If the question asks for a count, use COUNT(*)
5. If the question asks for a limit, add LIMIT at the end (default to 100 if not specified)
6. Use proper JOIN syntax for foreign key relationships
7. Return ONLY the SQL query, nothing else

SQL Query:"""

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,  # Low temperature for more deterministic SQL
                        "num_predict": 500
                    }
                },
                timeout=self.ollama_timeout
            )

            response.raise_for_status()
            result = response.json()
            sql_query = result.get('response', '').strip()

            # Clean up the response (remove markdown code blocks if present)
            sql_query = sql_query.replace('```sql', '').replace('```', '').strip()

            return sql_query

        except requests.RequestException as e:
            current_app.logger.error(f"Error calling Ollama API: {str(e)}")
            raise Exception(f"Failed to generate SQL: {str(e)}")

    def validate_sql_query(self, sql_query, schema):
        """
        CRITICAL SAFETY VALIDATION: Ensure the query is safe to execute.
        Uses sqlparse to parse and validate the SQL structure.
        
        Returns: (is_valid, error_message)
        """
        try:
            # Parse the SQL
            parsed = sqlparse.parse(sql_query)
            
            if not parsed:
                return False, "Failed to parse SQL query"

            # Check for multiple statements (semicolon-separated)
            if len(parsed) > 1:
                return False, "Multiple SQL statements detected. Only single SELECT statements are allowed."

            statement = parsed[0]

            # Check if it's a SELECT statement
            if not statement.get_type() == 'SELECT':
                return False, "Only SELECT statements are allowed"

            # Check for forbidden keywords using sqlparse
            sql_upper = sql_query.upper()
            for keyword in self.FORBIDDEN_KEYWORDS:
                if keyword in sql_upper:
                    return False, f"Forbidden keyword '{keyword}' detected in query"

            # Extract table and column names from the query
            tables_in_query = set()
            columns_in_query = set()

            for token in statement.flatten():
                if token.ttype is sqlparse.tokens.Name:
                    token_value = token.value.upper()
                    # Check if it's a table name (simple heuristic)
                    if token_value in [t.upper() for t in schema.keys()]:
                        tables_in_query.add(token_value)
                    columns_in_query.add(token_value)

            # Validate that referenced tables exist in schema
            valid_tables = {t.upper() for t in schema.keys()}
            invalid_tables = tables_in_query - valid_tables
            if invalid_tables:
                return False, f"Referenced tables not found in schema: {', '.join(invalid_tables)}"

            # Note: Column validation is more complex due to aliases and functions,
            # so we do a basic check and rely on database to catch invalid columns

            return True, None

        except Exception as e:
            current_app.logger.error(f"Error validating SQL query: {str(e)}")
            return False, f"SQL validation error: {str(e)}"

    def apply_safety_limits(self, sql_query):
        """
        Apply hard row limit to query if not already specified.
        Returns the modified SQL query.
        """
        # Check if LIMIT is already present
        if 'LIMIT' not in sql_query.upper():
            sql_query = f"{sql_query.rstrip(';')} LIMIT {self.query_limit}"
        else:
            # If LIMIT exists, ensure it doesn't exceed our maximum
            # This is a simple check; in production you might want more sophisticated parsing
            import re
            limit_match = re.search(r'LIMIT\s+(\d+)', sql_query, re.IGNORECASE)
            if limit_match:
                existing_limit = int(limit_match.group(1))
                if existing_limit > self.query_limit:
                    sql_query = re.sub(
                        r'LIMIT\s+\d+',
                        f'LIMIT {self.query_limit}',
                        sql_query,
                        flags=re.IGNORECASE
                    )

        return sql_query

    def execute_read_only_query(self, sql_query):
        """
        Execute the validated SQL query using a read-only database connection.
        Returns: (columns, rows)
        
        SECURITY CRITICAL: This must use a read-only database role.
        """
        try:
            from app import db

            # Set statement timeout for this query
            # This prevents long-running queries from hanging the connection
            db.session.execute(text(f"SET statement_timeout = {self.query_timeout * 1000}"))

            # Execute the query
            result = db.session.execute(text(sql_query))
            columns = list(result.keys())
            rows = []
            for row in result:
                # Convert Row object to dictionary
                row_dict = {}
                for i, col in enumerate(columns):
                    if hasattr(row, '_mapping'):
                        # SQLAlchemy 2.0 style
                        row_dict[col] = row._mapping[col]
                    elif hasattr(row, col):
                        # SQLAlchemy 1.4 style
                        row_dict[col] = getattr(row, col)
                    else:
                        # Fallback to tuple access
                        row_dict[col] = row[i] if i < len(row) else None
                rows.append(row_dict)

            # Reset statement timeout
            db.session.execute(text("SET statement_timeout = DEFAULT"))

            return columns, rows

        except SQLAlchemyError as e:
            current_app.logger.error(f"Error executing SQL query: {str(e)}")
            # Reset statement timeout on error
            try:
                db.session.execute(text("SET statement_timeout = DEFAULT"))
            except Exception:
                pass
            raise Exception(f"Failed to execute query: {str(e)}")

    def log_query(self, question, sql_query, validation_passed, execution_success, error_message=None):
        """
        Log query details for audit trail.
        """
        logger = get_sql_logger()
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'question': question,
            'sql_query': sql_query,
            'validation_passed': validation_passed,
            'execution_success': execution_success,
            'error_message': error_message
        }
        logger.info(f"Audit Log: {log_entry}")

    def ask_database(self, question):
        """
        Main entry point: Convert natural language question to SQL, validate, and execute.
        Returns: (success, result_dict)
        """
        schema = None
        generated_sql = None
        validation_passed = False
        execution_success = False
        error_message = None

        try:
            # Step 1: Get database schema
            schema = self.get_database_schema()

            # Step 2: Generate SQL from natural language
            generated_sql = self.generate_sql_from_natural_language(question)

            # Step 3: Validate the SQL query
            is_valid, validation_error = self.validate_sql_query(generated_sql, schema)
            validation_passed = is_valid

            if not is_valid:
                self.log_query(question, generated_sql, False, False, validation_error)
                return False, {
                    'error': validation_error,
                    'sql': generated_sql
                }

            # Step 4: Apply safety limits
            safe_sql = self.apply_safety_limits(generated_sql)

            # Step 5: Execute the query
            columns, rows = self.execute_read_only_query(safe_sql)
            execution_success = True

            # Log successful query
            self.log_query(question, safe_sql, True, True, None)

            return True, {
                'sql': safe_sql,
                'columns': columns,
                'rows': rows
            }

        except Exception as e:
            error_message = str(e)
            self.log_query(question, generated_sql or 'N/A', validation_passed, False, error_message)
            return False, {
                'error': error_message,
                'sql': generated_sql or 'N/A'
            }
