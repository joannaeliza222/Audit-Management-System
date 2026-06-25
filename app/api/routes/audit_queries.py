from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta
import json
import numpy as np

from app import db
from app.audit_models import AuditQuery, AuditQueryStatus, Commitment, CommitmentStatus
from app.services.document_parser import DocumentParser
from app.services.query_intelligence import QueryIntelligenceService
from app.services.commitment_tracker import CommitmentTracker
from app.services.version_tracker import VersionTracker
from app.services.analytics_service import AnalyticsService
from app.utils.embeddings import login_required, current_user, get_bert_embeddings, normalize, cleanup_queries_without_states
from app.utils.vector_support import serialize_vector

audit_bp = Blueprint('audit', __name__)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Services
doc_parser = DocumentParser()
intelligence_service = QueryIntelligenceService()
commitment_tracker = CommitmentTracker()
version_tracker = VersionTracker()
analytics_service = AnalyticsService()


@audit_bp.route('/queries', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def get_queries():
    """Get audit queries with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        # Filters
        state_name = request.args.get('state_name')
        status = request.args.get('status')
        priority = request.args.get('priority')
        assigned_to = request.args.get('assigned_to')
        
        # Date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build query
        query = AuditQuery.query
        
        # Filter out queries without state_name
        query = query.filter(AuditQuery.state_name.isnot(None))
        query = query.filter(AuditQuery.state_name != '')
        
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        if status:
            try:
                query = query.filter(AuditQuery.status == AuditQueryStatus(status))
            except ValueError:
                return jsonify({'error': 'Invalid status value'}), 400
        
        if priority:
            query = query.filter(AuditQuery.priority == priority)
        
        if assigned_to:
            query = query.filter(AuditQuery.assigned_official_email == assigned_to)
        
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(AuditQuery.date_received >= start_dt)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                query = query.filter(AuditQuery.date_received <= end_dt)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400
        
        # Order by date received (newest first)
        query = query.order_by(AuditQuery.date_received.desc())
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        results = []
        for audit_query in pagination.items:
            results.append({
                'id': audit_query.id,
                'query_id': audit_query.query_id,
                'state_name': audit_query.state_name,
                'date_received': audit_query.date_received.isoformat() if audit_query.date_received else None,
                'query_description': audit_query.query_description,
                'assigned_official': audit_query.assigned_official,
                'assigned_official_email': audit_query.assigned_official_email,
                'department': audit_query.department,
                'priority': audit_query.priority,
                'status': audit_query.status.value if audit_query.status else None,
                'response_provided': audit_query.response_provided,
                'response_date': audit_query.response_date.isoformat() if audit_query.response_date else None,
                'response_method': audit_query.response_method,
                'audit_type': audit_query.audit_type,
                'created_at': audit_query.created_at.isoformat() if audit_query.created_at else None,
                'commitments_count': len(audit_query.commitments),
                'overdue_commitments': len([c for c in audit_query.commitments if 
                                          c.target_date and c.target_date < datetime.now().date() and 
                                          c.status in [CommitmentStatus.pending, CommitmentStatus.in_progress]])
            })
        
        return jsonify({
            'queries': results,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting queries: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/queries', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def create_query():
    """Create a new audit query"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['query_id', 'state_name', 'date_received', 'query_description']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate state_name is not empty or null
        if not data['state_name'] or not data['state_name'].strip():
            return jsonify({'error': 'state_name cannot be empty or null'}), 400
        
        # Check if query_id already exists
        if AuditQuery.query.filter_by(query_id=data['query_id']).first():
            return jsonify({'error': 'Query ID already exists'}), 400
        
        # Parse date
        try:
            date_received = datetime.strptime(data['date_received'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date_received format. Use YYYY-MM-DD'}), 400
        
        # Create audit query
        audit_query = AuditQuery(
            query_id=data['query_id'],
            state_name=data['state_name'],
            date_received=date_received,
            query_description=data['query_description'],
            assigned_official=data.get('assigned_official'),
            assigned_official_email=data.get('assigned_official_email'),
            department=data.get('department'),
            priority=data.get('priority', 'medium'),
            audit_type=data.get('audit_type'),
            memo_id=data.get('memo_id'),
            audit_year=data.get('audit_year')
        )
        
        # Generate embedding
        search_text = f"{audit_query.query_description} {audit_query.state_name}"
        embedding = get_bert_embeddings(search_text)
        if embedding is not None:
            normalized_embedding = normalize(embedding) if hasattr(embedding, 'tolist') else embedding
            audit_query.embedding = serialize_vector(normalized_embedding)
        
        db.session.add(audit_query)
        db.session.commit()
        
        # Create version record
        version_tracker.create_version_snapshot(
            audit_query,
            'created',
            current_user().email if current_user() else 'system',
            'Query created via API'
        )
        
        return jsonify({
            'id': audit_query.id,
            'query_id': audit_query.query_id,
            'message': 'Query created successfully'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating query: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/queries/<int:query_id>', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def get_query(query_id):
    """Get detailed information about a specific audit query"""
    try:
        audit_query = AuditQuery.query.get_or_404(query_id)
        
        # Get commitments
        commitments = []
        for commitment in audit_query.commitments:
            commitments.append({
                'id': commitment.id,
                'commitment_text': commitment.commitment_text,
                'commitment_type': commitment.commitment_type,
                'target_date': commitment.target_date.isoformat() if commitment.target_date else None,
                'status': commitment.status.value if commitment.status else None,
                'detected_at': commitment.detected_at.isoformat() if commitment.detected_at else None,
                'completed_at': commitment.completed_at.isoformat() if commitment.completed_at else None,
                'responsible_party': commitment.responsible_party,
                'days_overdue': (datetime.now().date() - commitment.target_date).days 
                               if commitment.target_date and commitment.target_date < datetime.now().date() 
                               and commitment.status in [CommitmentStatus.pending, CommitmentStatus.in_progress] 
                               else 0
            })
        
        # Get version history
        history = version_tracker.get_change_timeline(query_id)
        
        return jsonify({
            'id': audit_query.id,
            'query_id': audit_query.query_id,
            'state_name': audit_query.state_name,
            'date_received': audit_query.date_received.isoformat() if audit_query.date_received else None,
            'query_description': audit_query.query_description,
            'assigned_official': audit_query.assigned_official,
            'assigned_official_email': audit_query.assigned_official_email,
            'department': audit_query.department,
            'priority': audit_query.priority,
            'status': audit_query.status.value if audit_query.status else None,
            'response_provided': audit_query.response_provided,
            'response_date': audit_query.response_date.isoformat() if audit_query.response_date else None,
            'response_method': audit_query.response_method,
            'audit_type': audit_query.audit_type,
            'memo_id': audit_query.memo_id,
            'audit_year': audit_query.audit_year,
            'source_document': audit_query.source_document,
            'created_at': audit_query.created_at.isoformat() if audit_query.created_at else None,
            'updated_at': audit_query.updated_at.isoformat() if audit_query.updated_at else None,
            'closed_at': audit_query.closed_at.isoformat() if audit_query.closed_at else None,
            'commitments': commitments,
            'history': history
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting query {query_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/queries/<int:query_id>', methods=['PUT'])
@login_required
@limiter.limit("20 per minute")
def update_query(query_id):
    """Update an audit query"""
    try:
        audit_query = AuditQuery.query.get_or_404(query_id)
        data = request.get_json()
        
        # Store previous state for version tracking
        previous_state = {
            'status': audit_query.status.value if audit_query.status else None,
            'assigned': audit_query.assigned_official,
            'priority': audit_query.priority,
            'response': audit_query.response_provided
        }
        
        # Track changes
        changes = []
        
        # Update fields
        if 'status' in data:
            try:
                new_status = AuditQueryStatus(data['status'])
                if audit_query.status != new_status:
                    audit_query.status = new_status
                    changes.append('status')
            except ValueError:
                return jsonify({'error': 'Invalid status value'}), 400
        
        if 'assigned_official' in data:
            if audit_query.assigned_official != data['assigned_official']:
                audit_query.assigned_official = data['assigned_official']
                changes.append('assigned')
        
        if 'assigned_official_email' in data:
            audit_query.assigned_official_email = data['assigned_official_email']
        
        if 'department' in data:
            audit_query.department = data['department']
        
        if 'priority' in data:
            if audit_query.priority != data['priority']:
                audit_query.priority = data['priority']
                changes.append('priority')
        
        if 'response_provided' in data:
            if audit_query.response_provided != data['response_provided']:
                audit_query.response_provided = data['response_provided']
                audit_query.response_date = datetime.now().date()
                changes.append('response')
                
                # Extract commitments from response
                if data['response_provided']:
                    commitment_tracker.create_commitment_from_response(
                        query_id, 
                        data['response_provided'],
                        current_user().email if current_user() else 'system'
                    )
        
        if 'response_method' in data:
            audit_query.response_method = data['response_method']
        
        if 'audit_type' in data:
            audit_query.audit_type = data['audit_type']
        
        # Update timestamp
        audit_query.updated_at = datetime.utcnow()
        
        # Update embedding if description changed
        if 'query_description' in data:
            audit_query.query_description = data['query_description']
            search_text = f"{audit_query.query_description} {audit_query.state_name}"
            embedding = get_bert_embeddings(search_text)
            if embedding is not None:
                normalized_embedding = normalize(embedding) if hasattr(embedding, 'tolist') else embedding
                audit_query.embedding = serialize_vector(normalized_embedding)
        
        # Set closed_at if status is closed
        if audit_query.status == AuditQueryStatus.closed and not audit_query.closed_at:
            audit_query.closed_at = datetime.utcnow()
        
        db.session.commit()
        
        # Create version records for changes
        new_state = {
            'status': audit_query.status.value if audit_query.status else None,
            'assigned': audit_query.assigned_official,
            'priority': audit_query.priority,
            'response': audit_query.response_provided
        }
        
        for change in changes:
            change_type = f"{change}_changed"
            version_tracker.create_version_snapshot(
                audit_query,
                change_type,
                current_user().email if current_user() else 'system',
                f"Updated {change} via API",
                previous_state,
                new_state
            )
        
        return jsonify({
            'message': 'Query updated successfully',
            'changes_made': changes
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating query {query_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/queries/<int:query_id>/similar', methods=['GET'])
@login_required
@limiter.limit("20 per minute")
def get_similar_queries(query_id):
    """Get similar queries based on content"""
    try:
        audit_query = AuditQuery.query.get_or_404(query_id)
        
        # Get similar queries
        similar = intelligence_service.find_similar_queries(
            audit_query.query_description,
            audit_query.state_name,
            limit=10
        )
        
        return jsonify({
            'query_id': query_id,
            'similar_queries': similar
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting similar queries for {query_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/queries/<int:query_id>/suggest', methods=['GET'])
@login_required
@limiter.limit("20 per minute")
def suggest_response(query_id):
    """Get response suggestions for a query"""
    try:
        audit_query = AuditQuery.query.get_or_404(query_id)
        
        # Analyze query intent
        analysis = intelligence_service.analyze_query_intent(audit_query.query_description)
        
        # Get suggestions
        suggestions = intelligence_service.suggest_responses(
            audit_query.query_description,
            analysis
        )
        
        return jsonify({
            'query_id': query_id,
            'analysis': analysis,
            'suggestions': suggestions
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting response suggestions for {query_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/documents/upload', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def upload_document():
    """Upload and process a document"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Process document
        doc_record = doc_parser.process_document(file, current_user().email if current_user() else 'system')
        
        # Get extracted items
        extracted_items = []
        for item in doc_record.extracted_items:
            extracted_items.append({
                'id': item.id,
                'item_type': item.item_type,
                'content': item.content[:200] + '...' if len(item.content) > 200 else item.content,
                'confidence_score': item.confidence_score,
                'page_number': item.page_number
            })
        
        return jsonify({
            'document_id': doc_record.id,
            'original_filename': doc_record.original_filename,
            'file_type': doc_record.file_type,
            'processing_status': doc_record.processing_status,
            'extracted_queries': doc_record.extracted_queries,
            'extracted_qa_pairs': doc_record.extracted_qa_pairs,
            'extraction_confidence': doc_record.extraction_confidence,
            'extracted_items': extracted_items
        })
        
    except Exception as e:
        current_app.logger.error(f"Error uploading document: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/commitments', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def get_commitments():
    """Get commitments with filtering"""
    try:
        state_name = request.args.get('state_name')
        status = request.args.get('status')
        commitment_type = request.args.get('type')
        
        # Base query
        query = Commitment.query
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        if status:
            try:
                query = query.filter(Commitment.status == CommitmentStatus(status))
            except ValueError:
                return jsonify({'error': 'Invalid status value'}), 400
        
        if commitment_type:
            query = query.filter(Commitment.commitment_type == commitment_type)
        
        # Order by target date
        query = query.order_by(Commitment.target_date.asc())
        
        commitments = query.limit(100).all()
        
        results = []
        for commitment in commitments:
            results.append({
                'id': commitment.id,
                'audit_query_id': commitment.audit_query_id,
                'query_id': commitment.audit_query.query_id if commitment.audit_query else None,
                'query_description': commitment.audit_query.query_description[:100] + '...' if commitment.audit_query and len(commitment.audit_query.query_description) > 100 else (commitment.audit_query.query_description if commitment.audit_query else None),
                'commitment_text': commitment.commitment_text,
                'commitment_type': commitment.commitment_type,
                'target_date': commitment.target_date.isoformat() if commitment.target_date else None,
                'status': commitment.status.value if commitment.status else None,
                'detected_at': commitment.detected_at.isoformat() if commitment.detected_at else None,
                'completed_at': commitment.completed_at.isoformat() if commitment.completed_at else None,
                'responsible_party': commitment.responsible_party,
                'days_overdue': (datetime.now().date() - commitment.target_date).days 
                               if commitment.target_date and commitment.target_date < datetime.now().date() 
                               and commitment.status in [CommitmentStatus.pending, CommitmentStatus.in_progress] 
                               else 0,
                'state_name': commitment.audit_query.state_name if commitment.audit_query else None
            })
        
        return jsonify({'commitments': results})
        
    except Exception as e:
        current_app.logger.error(f"Error getting commitments: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/commitments/<int:commitment_id>', methods=['PUT'])
@login_required
@limiter.limit("20 per minute")
def update_commitment(commitment_id):
    """Update commitment status"""
    try:
        data = request.get_json()
        
        if 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400
        
        try:
            new_status = CommitmentStatus(data['status'])
        except ValueError:
            return jsonify({'error': 'Invalid status value'}), 400
        
        success = commitment_tracker.update_commitment_status(
            commitment_id,
            new_status,
            data.get('notes'),
            current_user().email if current_user() else 'system'
        )
        
        if success:
            return jsonify({'message': 'Commitment updated successfully'})
        else:
            return jsonify({'error': 'Commitment not found'}), 404
        
    except Exception as e:
        current_app.logger.error(f"Error updating commitment {commitment_id}: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/analytics/dashboard', methods=['GET'])
@login_required
@limiter.limit("10 per minute")
def get_dashboard_analytics():
    """Get dashboard analytics"""
    try:
        state_name = request.args.get('state_name')
        days = request.args.get('days', 30, type=int)
        
        dashboard_data = analytics_service.get_dashboard_overview(state_name, days)
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard analytics: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/analytics/performance', methods=['GET'])
@login_required
@limiter.limit("10 per minute")
def get_performance_indicators():
    """Get performance indicators"""
    try:
        state_name = request.args.get('state_name')
        
        kpis = analytics_service.get_performance_indicators(state_name)
        
        return jsonify(kpis)
        
    except Exception as e:
        current_app.logger.error(f"Error getting performance indicators: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/analytics/state-comparison', methods=['GET'])
@login_required
@limiter.limit("5 per minute")
def get_state_comparison():
    """Compare metrics across states"""
    try:
        days = request.args.get('days', 30, type=int)
        
        comparison_data = analytics_service.get_state_comparison(days)
        
        return jsonify(comparison_data)
        
    except Exception as e:
        current_app.logger.error(f"Error getting state comparison: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@audit_bp.route('/cleanup-queries-without-states', methods=['POST'])
@login_required
@limiter.limit("1 per hour")
def cleanup_queries_without_states_endpoint():
    """Clean up queries without valid state_name (Admin only)"""
    try:
        # Check if user is admin
        user = current_user()
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        # Run cleanup
        result = cleanup_queries_without_states()
        
        return jsonify({
            'message': 'Cleanup completed successfully',
            'deleted_counts': result
        })
        
    except Exception as e:
        current_app.logger.error(f"Error during cleanup: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
