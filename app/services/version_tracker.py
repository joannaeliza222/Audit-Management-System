import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from flask import current_app
from sqlalchemy import and_, or_

from app import db
from app.audit_models import AuditQuery, QueryVersion, AuditQueryStatus


class VersionTracker:
    """Service for tracking version history and changes in audit queries"""
    
    def __init__(self):
        self.change_types = {
            'created': 'Query created',
            'response_updated': 'Response updated',
            'status_changed': 'Status changed',
            'reassigned': 'Query reassigned',
            'priority_changed': 'Priority changed',
            'commitment_updated': 'Commitment updated',
            'bulk_update': 'Bulk update applied'
        }
    
    def create_version_snapshot(self, audit_query: AuditQuery, change_type: str, 
                               changed_by: str, change_reason: str = None,
                               previous_state: Dict = None, new_state: Dict = None) -> QueryVersion:
        """Create a version snapshot for audit query changes"""
        
        # Get next version number
        version_number = self.get_next_version_number(audit_query.id)
        
        # Create full snapshot
        full_snapshot = self.create_full_snapshot(audit_query)
        
        # Create version record
        version = QueryVersion(
            audit_query_id=audit_query.id,
            version_number=version_number,
            change_type=change_type,
            changed_by=changed_by,
            change_reason=change_reason,
            change_timestamp=datetime.utcnow(),
            full_snapshot=full_snapshot
        )
        
        # Set specific change fields based on change type
        if change_type == 'status_changed' and previous_state and new_state:
            version.previous_status = previous_state.get('status')
            version.new_status = new_state.get('status')
        
        elif change_type == 'response_updated' and previous_state and new_state:
            version.previous_response = previous_state.get('response')
            version.new_response = new_state.get('response')
        
        elif change_type == 'reassigned' and previous_state and new_state:
            version.previous_assigned = previous_state.get('assigned')
            version.new_assigned = new_state.get('assigned')
        
        elif change_type == 'priority_changed' and previous_state and new_state:
            version.previous_priority = previous_state.get('priority')
            version.new_priority = new_state.get('priority')
        
        db.session.add(version)
        db.session.commit()
        
        current_app.logger.info(f"Created version {version_number} for query {audit_query.query_id}: {change_type}")
        return version
    
    def create_full_snapshot(self, audit_query: AuditQuery) -> Dict:
        """Create a complete JSON snapshot of the audit query"""
        snapshot = {
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
            'source_document': audit_query.source_document,
            'memo_id': audit_query.memo_id,
            'audit_year': audit_query.audit_year,
            'audit_type': audit_query.audit_type,
            'created_at': audit_query.created_at.isoformat() if audit_query.created_at else None,
            'updated_at': audit_query.updated_at.isoformat() if audit_query.updated_at else None,
            'closed_at': audit_query.closed_at.isoformat() if audit_query.closed_at else None,
            'commitments': [
                {
                    'id': c.id,
                    'text': c.commitment_text,
                    'type': c.commitment_type,
                    'target_date': c.target_date.isoformat() if c.target_date else None,
                    'status': c.status.value if c.status else None,
                    'detected_at': c.detected_at.isoformat() if c.detected_at else None,
                    'completed_at': c.completed_at.isoformat() if c.completed_at else None
                }
                for c in audit_query.commitments
            ]
        }
        
        return snapshot
    
    def get_next_version_number(self, audit_query_id: int) -> int:
        """Get next version number for audit query"""
        max_version = db.session.query(db.func.max(QueryVersion.version_number)).filter(
            QueryVersion.audit_query_id == audit_query_id
        ).scalar()
        
        return (max_version or 0) + 1
    
    def get_query_history(self, audit_query_id: int) -> List[QueryVersion]:
        """Get complete version history for an audit query"""
        return QueryVersion.query.filter_by(audit_query_id=audit_query_id).order_by(
            QueryVersion.version_number.desc()
        ).all()
    
    def get_change_timeline(self, audit_query_id: int) -> List[Dict]:
        """Get formatted timeline of changes for an audit query"""
        versions = self.get_query_history(audit_query_id)
        timeline = []
        
        for version in versions:
            timeline_item = {
                'version': version.version_number,
                'timestamp': version.change_timestamp.isoformat(),
                'change_type': version.change_type,
                'change_description': self.change_types.get(version.change_type, version.change_type),
                'changed_by': version.changed_by,
                'change_reason': version.change_reason,
                'details': self.get_change_details(version)
            }
            
            timeline.append(timeline_item)
        
        return timeline
    
    def get_change_details(self, version: QueryVersion) -> Dict:
        """Extract specific change details from version record"""
        details = {}
        
        if version.previous_status and version.new_status:
            details['status_change'] = {
                'from': version.previous_status.value if hasattr(version.previous_status, 'value') else version.previous_status,
                'to': version.new_status.value if hasattr(version.new_status, 'value') else version.new_status
            }
        
        if version.previous_response is not None or version.new_response is not None:
            details['response_change'] = {
                'from': version.previous_response[:200] + '...' if version.previous_response and len(version.previous_response) > 200 else version.previous_response,
                'to': version.new_response[:200] + '...' if version.new_response and len(version.new_response) > 200 else version.new_response
            }
        
        if version.previous_assigned != version.new_assigned:
            details['assignment_change'] = {
                'from': version.previous_assigned,
                'to': version.new_assigned
            }
        
        return details
    
    def restore_version(self, audit_query_id: int, version_number: int, restored_by: str) -> bool:
        """Restore audit query to a specific version"""
        version = QueryVersion.query.filter_by(
            audit_query_id=audit_query_id,
            version_number=version_number
        ).first()
        
        if not version or not version.full_snapshot:
            return False
        
        audit_query = AuditQuery.query.get(audit_query_id)
        if not audit_query:
            return False
        
        # Store current state for version tracking
        previous_state = self.create_full_snapshot(audit_query)
        
        # Restore from snapshot
        snapshot = version.full_snapshot
        
        audit_query.query_description = snapshot.get('query_description', audit_query.query_description)
        audit_query.assigned_official = snapshot.get('assigned_official', audit_query.assigned_official)
        audit_query.assigned_official_email = snapshot.get('assigned_official_email', audit_query.assigned_official_email)
        audit_query.department = snapshot.get('department', audit_query.department)
        audit_query.priority = snapshot.get('priority', audit_query.priority)
        audit_query.response_provided = snapshot.get('response_provided', audit_query.response_provided)
        audit_query.response_method = snapshot.get('response_method', audit_query.response_method)
        audit_query.audit_type = snapshot.get('audit_type', audit_query.audit_type)
        
        # Restore status
        if snapshot.get('status'):
            try:
                audit_query.status = AuditQueryStatus(snapshot['status'])
            except ValueError:
                current_app.logger.warning(f"Invalid status in snapshot: {snapshot['status']}")
        
        # Restore dates
        if snapshot.get('response_date'):
            try:
                audit_query.response_date = datetime.strptime(snapshot['response_date'], '%Y-%m-%d').date()
            except ValueError:
                pass
        
        audit_query.updated_at = datetime.utcnow()
        
        # Create version record for the restoration
        self.create_version_snapshot(
            audit_query,
            'version_restored',
            restored_by,
            f"Restored to version {version_number}",
            previous_state,
            snapshot
        )
        
        current_app.logger.info(f"Restored query {audit_query.query_id} to version {version_number}")
        return True
    
    def compare_versions(self, audit_query_id: int, version1: int, version2: int) -> Dict:
        """Compare two versions of an audit query"""
        v1 = QueryVersion.query.filter_by(audit_query_id=audit_query_id, version_number=version1).first()
        v2 = QueryVersion.query.filter_by(audit_query_id=audit_query_id, version_number=version2).first()
        
        if not v1 or not v2:
            return {'error': 'One or both versions not found'}
        
        snapshot1 = v1.full_snapshot or {}
        snapshot2 = v2.full_snapshot or {}
        
        differences = self._compare_snapshots(snapshot1, snapshot2)
        
        return {
            'version1': {
                'number': v1.version_number,
                'timestamp': v1.change_timestamp.isoformat(),
                'change_type': v1.change_type
            },
            'version2': {
                'number': v2.version_number,
                'timestamp': v2.change_timestamp.isoformat(),
                'change_type': v2.change_type
            },
            'differences': differences
        }
    
    def _compare_snapshots(self, snapshot1: Dict, snapshot2: Dict) -> Dict:
        """Compare two snapshots and return differences"""
        differences = {}
        
        # Compare key fields
        key_fields = [
            'query_description', 'assigned_official', 'department', 
            'priority', 'status', 'response_provided', 'audit_type'
        ]
        
        for field in key_fields:
            val1 = snapshot1.get(field)
            val2 = snapshot2.get(field)
            
            if val1 != val2:
                differences[field] = {
                    'from': val1,
                    'to': val2
                }
        
        # Compare commitments
        commitments1 = snapshot1.get('commitments', [])
        commitments2 = snapshot2.get('commitments', [])
        
        if len(commitments1) != len(commitments2):
            differences['commitments_count'] = {
                'from': len(commitments1),
                'to': len(commitments2)
            }
        
        return differences
    
    def get_change_statistics(self, state_name: str = None, days: int = 30) -> Dict:
        """Get statistics about query changes"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Base query
        query = QueryVersion.query.filter(
            QueryVersion.change_timestamp >= start_date,
            QueryVersion.change_timestamp <= end_date
        )
        
        if state_name:
            query = query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        # Total changes
        total_changes = query.count()
        
        # Changes by type
        changes_by_type = {}
        for change_type in self.change_types.keys():
            count = query.filter(QueryVersion.change_type == change_type).count()
            changes_by_type[change_type] = count
        
        # Most active users
        active_users = db.session.query(
            QueryVersion.changed_by,
            db.func.count(QueryVersion.id).label('change_count')
        ).filter(
            QueryVersion.change_timestamp >= start_date,
            QueryVersion.change_timestamp <= end_date
        ).group_by(QueryVersion.changed_by).order_by(
            db.desc('change_count')
        ).limit(10).all()
        
        # Queries with most changes
        most_changed_queries = db.session.query(
            AuditQuery.query_id,
            db.func.count(QueryVersion.id).label('change_count')
        ).join(QueryVersion).filter(
            QueryVersion.change_timestamp >= start_date,
            QueryVersion.change_timestamp <= end_date
        )
        
        if state_name:
            most_changed_queries = most_changed_queries.filter(AuditQuery.state_name == state_name)
        
        most_changed_queries = most_changed_queries.group_by(
            AuditQuery.id, AuditQuery.query_id
        ).order_by(db.desc('change_count')).limit(10).all()
        
        return {
            'period_days': days,
            'state': state_name or 'All States',
            'total_changes': total_changes,
            'changes_by_type': changes_by_type,
            'most_active_users': [{'user': user, 'changes': count} for user, count in active_users],
            'most_changed_queries': [{'query_id': query_id, 'changes': count} for query_id, count in most_changed_queries]
        }
    
    def track_bulk_update(self, audit_query_ids: List[int], update_data: Dict, 
                         updated_by: str) -> Dict:
        """Track bulk updates to multiple queries"""
        updated_count = 0
        failed_ids = []
        
        for query_id in audit_query_ids:
            try:
                audit_query = AuditQuery.query.get(query_id)
                if not audit_query:
                    failed_ids.append(query_id)
                    continue
                
                # Store previous state
                previous_state = {
                    'status': audit_query.status.value if audit_query.status else None,
                    'assigned': audit_query.assigned_official,
                    'priority': audit_query.priority,
                    'response': audit_query.response_provided
                }
                
                # Apply updates
                if 'status' in update_data:
                    audit_query.status = AuditQueryStatus(update_data['status'])
                
                if 'assigned_official' in update_data:
                    audit_query.assigned_official = update_data['assigned_official']
                
                if 'priority' in update_data:
                    audit_query.priority = update_data['priority']
                
                if 'response_provided' in update_data:
                    audit_query.response_provided = update_data['response_provided']
                
                audit_query.updated_at = datetime.utcnow()
                
                # Create version record
                self.create_version_snapshot(
                    audit_query,
                    'bulk_update',
                    updated_by,
                    f"Bulk update: {', '.join(update_data.keys())}",
                    previous_state,
                    update_data
                )
                
                updated_count += 1
                
            except Exception as e:
                current_app.logger.error(f"Failed to track bulk update for query {query_id}: {str(e)}")
                failed_ids.append(query_id)
        
        return {
            'updated_count': updated_count,
            'failed_count': len(failed_ids),
            'failed_ids': failed_ids
        }
    
    def export_query_history(self, audit_query_id: int, format: str = 'json') -> str:
        """Export complete query history in specified format"""
        versions = self.get_query_history(audit_query_id)
        audit_query = AuditQuery.query.get(audit_query_id)
        
        if not audit_query:
            return None
        
        export_data = {
            'query_info': {
                'query_id': audit_query.query_id,
                'state_name': audit_query.state_name,
                'current_status': audit_query.status.value if audit_query.status else None,
                'created_at': audit_query.created_at.isoformat() if audit_query.created_at else None,
                'total_versions': len(versions)
            },
            'versions': []
        }
        
        for version in versions:
            version_data = {
                'version_number': version.version_number,
                'timestamp': version.change_timestamp.isoformat(),
                'change_type': version.change_type,
                'changed_by': version.changed_by,
                'change_reason': version.change_reason,
                'snapshot': version.full_snapshot
            }
            export_data['versions'].append(version_data)
        
        if format.lower() == 'json':
            return json.dumps(export_data, indent=2, default=str)
        else:
            # For other formats, you could implement CSV, Excel export
            return json.dumps(export_data, indent=2, default=str)
    
    def cleanup_old_versions(self, days_to_keep: int = 365) -> int:
        """Clean up old version records to manage database size"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Keep only the latest version for queries older than cutoff
        old_versions = QueryVersion.query.filter(
            QueryVersion.change_timestamp < cutoff_date
        ).all()
        
        # Group by query and keep only the latest
        latest_versions = {}
        for version in old_versions:
            if version.audit_query_id not in latest_versions or version.version_number > latest_versions[version.audit_query_id].version_number:
                latest_versions[version.audit_query_id] = version
        
        # Delete versions that are not the latest
        deleted_count = 0
        for version in old_versions:
            if latest_versions.get(version.audit_query_id) != version:
                db.session.delete(version)
                deleted_count += 1
        
        db.session.commit()
        
        current_app.logger.info(f"Cleaned up {deleted_count} old version records (older than {days_to_keep} days)")
        return deleted_count
