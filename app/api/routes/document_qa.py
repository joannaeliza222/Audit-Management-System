import os
import json
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import logging

from ... import db
from ...services.document_qa_service import DocumentQAService
from ...services.llm_qa_service import LLMQAService
from ...utils.input_validation import sanitize_input, validate_file_upload
from ...utils.rate_limiting import rate_limit_check
from ...document_qa_models import (
    SecureDocument, QASession, QAConversation, 
    DocumentStatus, DocumentAccessLog
)

logger = logging.getLogger(__name__)

document_qa_bp = Blueprint('document_qa', __name__)

# Initialize services
doc_service = DocumentQAService()
llm_service = LLMQAService()


@document_qa_bp.route('/api/documents/upload', methods=['POST'])
@login_required
@rate_limit_check(limit=5, window=3600)  # 5 uploads per hour
def upload_document():
    """Upload a document for Q&A"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file
        is_valid, error_msg = doc_service.validate_file(file, file.filename)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Upload document
        document, message = doc_service.upload_document(
            current_user.id, 
            file, 
            file.filename
        )
        
        if document:
            return jsonify({
                'message': message,
                'document': {
                    'id': document.id,
                    'original_filename': document.original_filename,
                    'status': document.status.value,
                    'created_at': document.created_at.isoformat()
                }
            }), 201
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500


@document_qa_bp.route('/api/documents', methods=['GET'])
@login_required
def get_documents():
    """Get user's documents"""
    try:
        status_filter = request.args.get('status')
        status = None
        if status_filter:
            try:
                status = DocumentStatus(status_filter)
            except ValueError:
                return jsonify({'error': 'Invalid status'}), 400
        
        documents = doc_service.get_user_documents(current_user.id, status)
        
        return jsonify({
            'documents': [
                {
                    'id': doc.id,
                    'original_filename': doc.original_filename,
                    'file_size': doc.file_size,
                    'mime_type': doc.mime_type,
                    'status': doc.status.value,
                    'page_count': doc.page_count,
                    'word_count': doc.word_count,
                    'created_at': doc.created_at.isoformat(),
                    'updated_at': doc.updated_at.isoformat(),
                    'processing_completed_at': doc.processing_completed_at.isoformat() if doc.processing_completed_at else None
                }
                for doc in documents
            ]
        })
        
    except Exception as e:
        logger.error(f"Get documents error: {e}")
        return jsonify({'error': 'Failed to retrieve documents'}), 500


@document_qa_bp.route('/api/documents/<int:document_id>', methods=['GET'])
@login_required
def get_document(document_id):
    """Get specific document details"""
    try:
        document = SecureDocument.query.filter_by(
            id=document_id, 
            user_id=current_user.id
        ).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Log access
        doc_service._log_access(document_id, current_user.id, 'view')
        
        return jsonify({
            'document': {
                'id': document.id,
                'original_filename': document.original_filename,
                'file_size': document.file_size,
                'mime_type': document.mime_type,
                'status': document.status.value,
                'page_count': document.page_count,
                'word_count': document.word_count,
                'extracted_text_length': document.extracted_text_length,
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat(),
                'processing_completed_at': document.processing_completed_at.isoformat() if document.processing_completed_at else None,
                'processing_error': document.processing_error
            }
        })
        
    except Exception as e:
        logger.error(f"Get document error: {e}")
        return jsonify({'error': 'Failed to retrieve document'}), 500


@document_qa_bp.route('/api/documents/<int:document_id>', methods=['DELETE'])
@login_required
def delete_document(document_id):
    """Delete a document"""
    try:
        success = doc_service.delete_document(document_id, current_user.id)
        
        if success:
            return jsonify({'message': 'Document deleted successfully'})
        else:
            return jsonify({'error': 'Document not found or cannot be deleted'}), 404
            
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        return jsonify({'error': 'Failed to delete document'}), 500


@document_qa_bp.route('/api/documents/<int:document_id>/qa-session', methods=['POST'])
@login_required
def create_qa_session(document_id):
    """Create Q&A session for a document"""
    try:
        # Verify document exists and belongs to user
        document = SecureDocument.query.filter_by(
            id=document_id, 
            user_id=current_user.id,
            status=DocumentStatus.ready
        ).first()
        
        if not document:
            return jsonify({'error': 'Document not found or not ready'}), 404
        
        session_name = request.json.get('session_name') if request.is_json else None
        
        session = doc_service.create_qa_session(
            current_user.id, 
            document_id, 
            session_name
        )
        
        return jsonify({
            'session': {
                'id': session.id,
                'session_token': session.session_token,
                'session_name': session.session_name,
                'document_id': session.document_id,
                'created_at': session.created_at.isoformat()
            }
        }), 201
        
    except Exception as e:
        logger.error(f"Create Q&A session error: {e}")
        return jsonify({'error': 'Failed to create session'}), 500


@document_qa_bp.route('/api/qa-sessions/<int:session_id>/ask', methods=['POST'])
@login_required
@rate_limit_check(limit=20, window=3600)  # 20 questions per hour
def ask_question(session_id):
    """Ask a question in a Q&A session"""
    try:
        # Verify session exists and belongs to user
        session = QASession.query.filter_by(
            id=session_id, 
            user_id=current_user.id
        ).first()
        
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Get question from request
        if not request.is_json or 'question' not in request.json:
            return jsonify({'error': 'Question is required'}), 400
        
        question = sanitize_input(request.json['question'])
        if not question or len(question.strip()) < 3:
            return jsonify({'error': 'Question must be at least 3 characters'}), 400
        
        # Get optional model preference
        model = request.json.get('model', 'gpt-3.5-turbo')
        
        # Ask question
        answer, confidence, sources = doc_service.ask_question(session_id, question)
        
        return jsonify({
            'answer': answer,
            'confidence': confidence,
            'sources': sources,
            'question': question,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ask question error: {e}")
        return jsonify({'error': 'Failed to process question'}), 500


@document_qa_bp.route('/api/qa-sessions/<int:session_id>/conversations', methods=['GET'])
@login_required
def get_conversations(session_id):
    """Get conversation history for a session"""
    try:
        # Verify session exists and belongs to user
        session = QASession.query.filter_by(
            id=session_id, 
            user_id=current_user.id
        ).first()
        
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        conversations = QAConversation.query.filter_by(
            session_id=session_id
        ).order_by(QAConversation.created_at.desc()).all()
        
        return jsonify({
            'conversations': [
                {
                    'id': conv.id,
                    'question': conv.question,
                    'answer': conv.answer,
                    'confidence_score': conv.confidence_score,
                    'response_time_ms': conv.response_time_ms,
                    'model_used': conv.model_used,
                    'context_length': conv.context_length,
                    'created_at': conv.created_at.isoformat(),
                    'sources': json.loads(conv.relevant_chunks) if conv.relevant_chunks else []
                }
                for conv in conversations
            ]
        })
        
    except Exception as e:
        logger.error(f"Get conversations error: {e}")
        return jsonify({'error': 'Failed to retrieve conversations'}), 500


@document_qa_bp.route('/api/qa-sessions', methods=['GET'])
@login_required
def get_qa_sessions():
    """Get user's Q&A sessions"""
    try:
        document_id = request.args.get('document_id', type=int)
        
        query = QASession.query.filter_by(user_id=current_user.id)
        if document_id:
            query = query.filter_by(document_id=document_id)
        
        sessions = query.order_by(QASession.last_activity_at.desc()).all()
        
        return jsonify({
            'sessions': [
                {
                    'id': session.id,
                    'session_name': session.session_name,
                    'document_id': session.document_id,
                    'document_filename': session.document.original_filename,
                    'question_count': session.question_count,
                    'last_activity_at': session.last_activity_at.isoformat(),
                    'created_at': session.created_at.isoformat()
                }
                for session in sessions
            ]
        })
        
    except Exception as e:
        logger.error(f"Get Q&A sessions error: {e}")
        return jsonify({'error': 'Failed to retrieve sessions'}), 500


@document_qa_bp.route('/api/llm/models', methods=['GET'])
@login_required
def get_llm_models():
    """Get available LLM models"""
    try:
        models = llm_service.get_available_models()
        api_status = llm_service.validate_api_keys()
        
        return jsonify({
            'models': models,
            'api_status': api_status,
            'default_model': llm_service.default_model
        })
        
    except Exception as e:
        logger.error(f"Get LLM models error: {e}")
        return jsonify({'error': 'Failed to retrieve models'}), 500


@document_qa_bp.route('/api/documents/<int:document_id>/status', methods=['GET'])
@login_required
def get_document_status(document_id):
    """Get document processing status"""
    try:
        document = SecureDocument.query.filter_by(
            id=document_id, 
            user_id=current_user.id
        ).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get chunk count for processed documents
        chunk_count = 0
        if document.status == DocumentStatus.ready:
            chunk_count = document.chunks.count()
        
        return jsonify({
            'status': document.status.value,
            'processing_started_at': document.processing_started_at.isoformat() if document.processing_started_at else None,
            'processing_completed_at': document.processing_completed_at.isoformat() if document.processing_completed_at else None,
            'processing_error': document.processing_error,
            'chunk_count': chunk_count,
            'word_count': document.word_count,
            'page_count': document.page_count
        })
        
    except Exception as e:
        logger.error(f"Get document status error: {e}")
        return jsonify({'error': 'Failed to get document status'}), 500


@document_qa_bp.route('/api/documents/<int:document_id>/download', methods=['GET'])
@login_required
@rate_limit_check(limit=10, window=3600)  # 10 downloads per hour
def download_document(document_id):
    """Download original document"""
    try:
        document = SecureDocument.query.filter_by(
            id=document_id, 
            user_id=current_user.id
        ).first()
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        if not os.path.exists(document.file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Log download
        doc_service._log_access(document_id, current_user.id, 'download')
        
        return send_file(
            document.file_path,
            as_attachment=True,
            download_name=document.original_filename,
            mimetype=document.mime_type
        )
        
    except Exception as e:
        logger.error(f"Download document error: {e}")
        return jsonify({'error': 'Failed to download document'}), 500


@document_qa_bp.route('/api/documents/stats', methods=['GET'])
@login_required
def get_document_stats():
    """Get user's document statistics"""
    try:
        # Document counts by status
        total_docs = SecureDocument.query.filter_by(user_id=current_user.id).count()
        ready_docs = SecureDocument.query.filter_by(
            user_id=current_user.id, 
            status=DocumentStatus.ready
        ).count()
        processing_docs = SecureDocument.query.filter_by(
            user_id=current_user.id, 
            status=DocumentStatus.processing
        ).count()
        failed_docs = SecureDocument.query.filter_by(
            user_id=current_user.id, 
            status=DocumentStatus.failed
        ).count()
        
        # Q&A session stats
        total_sessions = QASession.query.filter_by(user_id=current_user.id).count()
        total_questions = QAConversation.query.filter_by(user_id=current_user.id).count()
        
        # Storage stats
        total_size = db.session.query(
            db.func.sum(SecureDocument.file_size)
        ).filter_by(user_id=current_user.id).scalar() or 0
        
        return jsonify({
            'documents': {
                'total': total_docs,
                'ready': ready_docs,
                'processing': processing_docs,
                'failed': failed_docs
            },
            'qa_sessions': {
                'total': total_sessions,
                'total_questions': total_questions
            },
            'storage': {
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
        })
        
    except Exception as e:
        logger.error(f"Get document stats error: {e}")
        return jsonify({'error': 'Failed to retrieve statistics'}), 500
