import os
import io
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

from ...services.document_ingestion import DocumentIngestionService
from ...services.document_qa import DocumentQAService
from ...services.document_security import DocumentSecurityService
from ...services.vector_store import VectorStoreService


# Create blueprint
documents_bp = Blueprint('documents', __name__, url_prefix='/api/documents')


def get_document_services():
    """Get document service instances with proper configuration"""
    encryption_key = current_app.config.get('DOCUMENT_ENCRYPTION_KEY')
    if not encryption_key:
        raise ValueError("DOCUMENT_ENCRYPTION_KEY must be configured")
    
    ingestion_service = DocumentIngestionService(encryption_key)
    qa_service = DocumentQAService()
    vector_service = VectorStoreService()
    
    return ingestion_service, qa_service, vector_service


@documents_bp.route('/upload', methods=['POST'])
@login_required
def upload_document():
    """Upload a document for processing"""
    try:
        # Validate file presence
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get file info
        filename = file.filename
        mime_type = file.mimetype or 'application/octet-stream'
        
        # Get services
        ingestion_service, _, _ = get_document_services()
        
        # Upload document
        result = ingestion_service.upload_document(
            user_id=current_user.id,
            file_buffer=file,
            filename=filename,
            mime_type=mime_type,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'document_id': result['document_id'],
                'status': result['status'],
                'chunk_count': result['chunk_count'],
                'has_injection': result.get('has_injection', False)
            }), 201
        else:
            return jsonify({'error': result['error']}), 400
            
    except RequestEntityTooLarge:
        return jsonify({'error': 'File size exceeds maximum allowed limit'}), 413
    except Exception as e:
        current_app.logger.error(f"Error in upload_document: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/list', methods=['GET'])
@login_required
def list_documents():
    """List user's documents"""
    try:
        ingestion_service, _, _ = get_document_services()
        
        documents = ingestion_service.list_documents(current_user.id)
        
        return jsonify({
            'success': True,
            'documents': documents,
            'count': len(documents)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in list_documents: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/<document_id>', methods=['DELETE'])
@login_required
def delete_document(document_id):
    """Delete a document"""
    try:
        ingestion_service, _, _ = get_document_services()
        
        result = ingestion_service.delete_document(
            user_id=current_user.id,
            document_id=document_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        if result['success']:
            return jsonify({'success': True, 'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error in delete_document: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/<document_id>/content', methods=['GET'])
@login_required
def get_document_content(document_id):
    """Get decrypted document content"""
    try:
        ingestion_service, _, _ = get_document_services()
        
        content = ingestion_service.get_document_content(
            user_id=current_user.id,
            document_id=document_id
        )
        
        if content is None:
            return jsonify({'error': 'Document not found'}), 404
        
        return jsonify({
            'success': True,
            'content': content
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_document_content: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/<document_id>/chunks', methods=['GET'])
@login_required
def get_document_chunks(document_id):
    """Get document chunks"""
    try:
        include_flagged = request.args.get('include_flagged', 'false').lower() == 'true'
        
        ingestion_service, _, _ = get_document_services()
        
        chunks = ingestion_service.get_document_chunks(
            user_id=current_user.id,
            document_id=document_id,
            include_flagged=include_flagged
        )
        
        return jsonify({
            'success': True,
            'chunks': chunks,
            'count': len(chunks)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_document_chunks: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/ask', methods=['POST'])
@login_required
def ask_question():
    """Ask a question about documents"""
    try:
        data = request.get_json()
        if not data or 'question' not in data:
            return jsonify({'error': 'Question is required'}), 400
        
        question = data['question'].strip()
        if not question:
            return jsonify({'error': 'Question cannot be empty'}), 400
        
        # Get options from request
        options = {
            'top_k': data.get('top_k', 5),
            'similarity_threshold': data.get('similarity_threshold', 0.72),
            'include_flagged': data.get('include_flagged', False)
        }
        
        # Validate options
        if not 1 <= options['top_k'] <= 20:
            return jsonify({'error': 'top_k must be between 1 and 20'}), 400
        
        if not 0.0 <= options['similarity_threshold'] <= 1.0:
            return jsonify({'error': 'similarity_threshold must be between 0.0 and 1.0'}), 400
        
        _, qa_service, _ = get_document_services()
        
        result = qa_service.ask_question(
            user_id=current_user.id,
            question_text=question,
            options=options,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'success': True,
            'answer': result['answer'],
            'sources': result.get('sources', []),
            'model': result.get('model'),
            'tokens_used': result.get('tokens_used', 0),
            'chunks_found': result.get('chunks_found', 0),
            'injection_detected': result.get('injection_detected', False)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in ask_question: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/search', methods=['POST'])
@login_required
def search_documents():
    """Search within documents"""
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({'error': 'Query is required'}), 400
        
        query = data['query'].strip()
        if not query:
            return jsonify({'error': 'Query cannot be empty'}), 400
        
        # Get options
        document_id = data.get('document_id')  # Optional: search within specific document
        top_k = data.get('top_k', 10)
        similarity_threshold = data.get('similarity_threshold', 0.5)
        include_flagged = data.get('include_flagged', False)
        
        _, _, vector_service = get_document_services()
        
        if document_id:
            # Search within specific document
            chunks = vector_service.search_by_document(
                user_id=current_user.id,
                document_id=document_id,
                query_text=query
            )
        else:
            # Hybrid search across all documents
            chunks = vector_service.hybrid_search(
                user_id=current_user.id,
                query_text=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                include_flagged=include_flagged
            )
        
        return jsonify({
            'success': True,
            'chunks': chunks,
            'count': len(chunks)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in search_documents: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/statistics', methods=['GET'])
@login_required
def get_statistics():
    """Get user's document statistics"""
    try:
        _, qa_service, vector_service = get_document_services()
        
        # Get usage statistics
        usage_stats = qa_service.get_usage_statistics(current_user.id)
        
        # Get vector store statistics
        vector_stats = vector_service.get_user_statistics(current_user.id)
        
        return jsonify({
            'success': True,
            'usage': usage_stats,
            'vector': vector_stats
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_statistics: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/conversation', methods=['GET'])
@login_required
def get_conversation_history():
    """Get conversation history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        
        _, qa_service, _ = get_document_services()
        
        history = qa_service.get_conversation_history(current_user.id, limit)
        
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in get_conversation_history: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/delete-all', methods=['POST'])
@login_required
def delete_all_user_data():
    """Delete all user data (GDPR compliance)"""
    try:
        data = request.get_json() or {}
        
        # Get options
        options = {
            'dry_run': data.get('dry_run', False),
            'purge_audit_log': data.get('purge_audit_log', False),
            'reason': data.get('reason', 'user_request')
        }
        
        # Validate reason
        valid_reasons = ['gdpr_erasure_request', 'account_closure', 'user_request']
        if options['reason'] not in valid_reasons:
            return jsonify({'error': f'Invalid reason. Must be one of: {valid_reasons}'}), 400
        
        _, qa_service, _ = get_document_services()
        
        result = qa_service.delete_all_user_data(
            user_id=current_user.id,
            options=options,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'success': result['success'],
            'dry_run': result.get('dry_run', False),
            'partial_failure': result.get('partial_failure', False),
            'failed_stores': result.get('failed_stores', []),
            'documents_deleted': result.get('documents_deleted', 0),
            'chunks_deleted': result.get('chunks_deleted', 0),
            'audit_entries_anonymised': result.get('audit_entries_anonymised', 0),
            'gdpr_token': result.get('gdpr_token'),
            'reason': result.get('reason')
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in delete_all_user_data: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@documents_bp.route('/health', methods=['GET'])
@login_required
def health_check():
    """Health check for document services"""
    try:
        # Test service initialization
        ingestion_service, qa_service, vector_service = get_document_services()
        
        # Test vector store connectivity
        stats = vector_service.get_user_statistics(current_user.id)
        
        return jsonify({
            'success': True,
            'status': 'healthy',
            'services': {
                'ingestion': 'available',
                'qa': 'available',
                'vector_store': 'available'
            },
            'user_stats': stats
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in health_check: {e}")
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@documents_bp.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({'error': 'File size exceeds maximum allowed limit'}), 413


@documents_bp.errorhandler(400)
def bad_request(e):
    """Handle bad request errors"""
    return jsonify({'error': 'Bad request'}), 400


@documents_bp.errorhandler(401)
def unauthorized(e):
    """Handle unauthorized errors"""
    return jsonify({'error': 'Authentication required'}), 401


@documents_bp.errorhandler(403)
def forbidden(e):
    """Handle forbidden errors"""
    return jsonify({'error': 'Access denied'}), 403


@documents_bp.errorhandler(404)
def not_found(e):
    """Handle not found errors"""
    return jsonify({'error': 'Resource not found'}), 404


@documents_bp.errorhandler(500)
def internal_error(e):
    """Handle internal server errors"""
    current_app.logger.error(f"Internal server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500
