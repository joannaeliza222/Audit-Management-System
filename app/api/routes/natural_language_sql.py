"""
Natural Language SQL API Routes

Provides REST API endpoint for natural language to SQL conversion.
All queries are validated to be SELECT-only and executed with read-only access.

SECURITY CRITICAL:
- All SQL queries are validated before execution
- Uses read-only database role
- Applies hard row limits and query timeouts
- Logs all queries for audit trail
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user, login_required
from app.services.natural_language_sql import NaturalLanguageSQLService

natural_language_sql_bp = Blueprint('natural_language_sql', __name__)


@natural_language_sql_bp.route('/api/ask-db', methods=['POST'])
@login_required
def ask_database():
    """
    Convert natural language question to SQL and execute.

    Request body: { "question": "<user's natural language question>" }

    Returns: {
        "success": true/false,
        "sql": "<the query that ran>",
        "columns": [...],
        "rows": [...],
        "error": "<error message if failed>"
    }
    """
    try:
        # Validate request
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400

        data = request.get_json()
        question = data.get('question', '').strip()

        if not question:
            return jsonify({
                'success': False,
                'error': 'Question is required'
            }), 400

        # Initialize service
        service = NaturalLanguageSQLService()

        # Process the question
        success, result = service.ask_database(question)

        if success:
            return jsonify({
                'success': True,
                'sql': result['sql'],
                'columns': result['columns'],
                'rows': result['rows']
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error'],
                'sql': result.get('sql', 'N/A')
            }), 400

    except Exception as e:
        current_app.logger.error(f"Error in ask_database endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred'
        }), 500
