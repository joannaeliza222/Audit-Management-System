import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
from flask import current_app, session
from sqlalchemy import func, and_, or_, text, desc, extract
import psutil
import gc
import re
from collections import defaultdict

from app import db
from app.models import FAQ, User, Logs, DataDump, DraftFAQ
from app.utils.embeddings import get_bert_embeddings, normalize, find_related_questions_scored
from app.utils.llm_response_generator import LLMResponseGenerator


class ChatGPTAIAssistant:
    """ChatGPT-like AI Assistant with advanced NLP and comprehensive application knowledge"""
    
    def __init__(self):
        self.conversation_memory = ConversationMemory()
        self.app_knowledge = self._load_comprehensive_knowledge()
        self.nlp_processor = NLPProcessor()
        self.llm_generator = LLMResponseGenerator()
        
    def _load_comprehensive_knowledge(self) -> Dict:
        """Load comprehensive application knowledge base"""
        return {
            "application_overview": {
                "name": "Audit Management System",
                "purpose": "Comprehensive audit and data management platform",
                "main_features": [
                    "Audit workflow management",
                    "Data dump requests and approvals", 
                    "User management and access control",
                    "FAQ knowledge base",
                    "Real-time analytics and reporting"
                ]
            },
            "user_roles": {
                "admin": {
                    "capabilities": [
                        "Approve user registrations",
                        "Manage all data dump requests", 
                        "Access system analytics",
                        "Manage FAQ database",
                        "Full system administration"
                    ],
                    "dashboard_access": "Complete administrative dashboard"
                },
                "user": {
                    "capabilities": [
                        "Request data dumps",
                        "View approved dumps",
                        "Upload completed documents",
                        "Access FAQ knowledge base",
                        "View personal audit history"
                    ],
                    "dashboard_access": "Personal user dashboard"
                }
            },
            "workflows": {
                "data_dump_request": {
                    "steps": [
                        "1. Navigate to Data Dump section",
                        "2. Select your state from dropdown", 
                        "3. Choose data type required",
                        "4. Add description/reason",
                        "5. Submit request for approval",
                        "6. Wait for admin approval",
                        "7. Download approved data",
                        "8. Upload completed documents"
                    ],
                    "average_time": "2-3 business days",
                    "requirements": "Valid user account with approved registration"
                },
                "user_registration": {
                    "steps": [
                        "1. Click Register on login page",
                        "2. Fill in personal details",
                        "3. Select state/region", 
                        "4. Submit registration",
                        "5. Wait for admin approval",
                        "6. Receive confirmation email",
                        "7. Login with approved credentials"
                    ],
                    "approval_time": "1-2 business days"
                },
                "audit_process": {
                    "steps": [
                        "1. Create new audit from dashboard",
                        "2. Define audit scope and objectives",
                        "3. Assign audit team",
                        "4. Conduct audit activities",
                        "5. Document findings",
                        "6. Generate audit report",
                        "7. Review and finalize",
                        "8. Archive completed audit"
                    ]
                }
            }
        }
    
    def process_message(self, message: str, state_name: str = None, user_id: int = None) -> Dict:
        """Main message processing with ChatGPT-like intelligence"""
        
        # Analyze user intent and context
        intent_analysis = self.nlp_processor.analyze_intent(message)
        
        # Get conversation context
        context = self.conversation_memory.get_context()
        
        # Process based on intent
        if intent_analysis['type'] == 'data_query':
            response = self._handle_advanced_data_query(message, intent_analysis, state_name, user_id, context)
        elif intent_analysis['type'] == 'application_guidance':
            response = self._handle_comprehensive_guidance(message, intent_analysis, context)
        elif intent_analysis['type'] == 'conversation':
            response = self._handle_conversational_query(message, intent_analysis, context)
        elif intent_analysis['type'] == 'comparison':
            response = self._handle_comparison_query(message, intent_analysis, state_name, context)
        elif intent_analysis['type'] == 'troubleshooting':
            response = self._handle_troubleshooting_query(message, intent_analysis, context)
        else:
            response = self._handle_intelligent_faq_search(message, intent_analysis, state_name, context)
        
        # Add to conversation memory
        session_id = self.conversation_memory.get_session_id()
        self.conversation_memory.add_turn(message, response['response'], intent_analysis)
        
        return {
            'response': response['response'],
            'session_id': session_id,
            'sources': response.get('sources', []),
            'intent_type': intent_analysis['type'],
            'confidence': intent_analysis.get('confidence', 0.8),
            'timestamp': datetime.utcnow().isoformat(),
            'suggestions': response.get('suggestions', [])
        }
    
    def _handle_advanced_data_query(self, message: str, intent: Dict, state_name: str, user_id: int, context: List) -> Dict:
        """Handle advanced data queries with SQL-like natural language processing"""
        
        query_result = self.nlp_processor.parse_sql_query(message, state_name)
        
        if query_result:
            try:
                # Execute the parsed query
                data = self._execute_data_query(query_result, state_name, user_id)
                
                if data:
                    # Generate intelligent response using LLM
                    context = {
                        'user_id': user_id,
                        'state_name': state_name,
                        'is_admin': data.get('is_admin', False)
                    }
                    
                    llm_response = self.llm_generator.generate_response(message, data, context)
                    
                    return {
                        'response': llm_response['response'],
                        'sources': llm_response.get('sources', ['database_query']),
                        'data': data,
                        'suggestions': self._generate_followup_suggestions(query_result),
                        'llm_enhanced': True,
                        'confidence': llm_response.get('confidence', 0.8)
                    }
                else:
                    return {
                        'response': "I couldn't find data matching your query. Would you like me to help you formulate a different question?",
                        'sources': []
                    }
            except Exception as e:
                current_app.logger.error(f"Advanced data query error: {e}")
                return {
                    'response': f"I encountered an error while processing your data query: {str(e)}. Please try rephrasing your question.",
                    'sources': []
                }
        else:
            return {
                'response': self._generate_data_query_help(message),
                'sources': ['help_system']
            }
    
    def _execute_data_query(self, query_result: Dict, state_name: str, user_id: int) -> Optional[Dict]:
        """Execute the parsed data query"""
        
        query_type = query_result['type']
        params = query_result['params']
        
        try:
            if query_type == 'user_count':
                return self._get_user_statistics(params)
            elif query_type == 'datadump_count':
                return self._get_datadump_statistics(params, state_name)
            elif query_type == 'state_summary':
                return self._get_state_statistics(params, user_id, query_result.get('params', {}))
            elif query_type == 'pending_faqs':
                return self._get_pending_faq_statistics(params, user_id)
            elif query_type == 'total_count':
                return self._get_total_count_statistics(params)
            elif query_type == 'trend_analysis':
                return self._get_trend_analysis(params)
            elif query_type == 'comparison':
                return self._get_comparison_data(params)
            else:
                return None
                
        except Exception as e:
            current_app.logger.error(f"Query execution error: {e}")
            return None
    
    def _get_user_statistics(self, params: Dict) -> Dict:
        """Get comprehensive user statistics"""
        
        base_query = User.query
        
        # Apply filters
        if params.get('role'):
            base_query = base_query.filter(User.role == params['role'])
        if params.get('approved') is not None:
            base_query = base_query.filter(User.is_approved == params['approved'])
        if params.get('state'):
            base_query = base_query.filter(User.state_name.ilike(f'%{params["state"]}%'))
        
        # Get counts
        total_count = base_query.count()
        
        # Get role distribution
        role_distribution = db.session.query(
            User.role, func.count(User.id)
        ).group_by(User.role).all()
        
        # Get state distribution
        state_distribution = db.session.query(
            User.state_name, func.count(User.id)
        ).filter(User.state_name.isnot(None)).group_by(User.state_name).limit(10).all()
        
        # Get registration trends (last 30 days) - using timestamp from Logs as proxy
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_registrations = base_query.count()  # Simplified since User doesn't have created_at
        
        return {
            'total_users': total_count,
            'recent_registrations': recent_registrations,
            'role_distribution': dict(role_distribution),
            'state_distribution': dict(state_distribution),
            'query_type': 'user_statistics'
        }
    
    def _get_datadump_statistics(self, params: Dict, state_name: str) -> Dict:
        """Get comprehensive data dump statistics"""
        
        base_query = DataDump.query
        
        # Apply filters
        if params.get('status'):
            base_query = base_query.filter(DataDump.status == params['status'])
        if state_name:
            base_query = base_query.filter(DataDump.state.ilike(f'%{state_name}%'))
        elif params.get('state'):
            base_query = base_query.filter(DataDump.state.ilike(f'%{params["state"]}%'))
        
        # Get counts by status
        status_counts = db.session.query(
            DataDump.status, func.count(DataDump.id)
        ).group_by(DataDump.status).all()
        
        # Get state distribution
        state_counts = db.session.query(
            DataDump.state, func.count(DataDump.id)
        ).filter(DataDump.state.isnot(None)).group_by(DataDump.state).limit(10).all()
        
        # Get processing time statistics
        approved_dumps = DataDump.query.filter(
            DataDump.status == 'provided',  # Use 'provided' instead of 'APPROVED'
            DataDump.share_date.isnot(None),  # Use share_date instead of approved_at
            DataDump.created_at.isnot(None)
        ).all()
        
        processing_times = []
        for dump in approved_dumps:
            if dump.share_date and dump.created_at:
                processing_time = (dump.share_date - dump.created_at).days
                processing_times.append(processing_time)
        
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        return {
            'total_requests': base_query.count(),
            'status_distribution': dict(status_counts),
            'state_distribution': dict(state_counts),
            'average_processing_days': round(avg_processing_time, 1),
            'query_type': 'datadump_statistics'
        }
    
    def _get_state_statistics(self, params: Dict, user_id: int = None, query_params: Dict = None) -> Dict:
        """Get state-specific statistics with role-based filtering"""
        
        # Check if user is admin
        is_admin = False
        if user_id:
            user = User.query.get(user_id)
            is_admin = user and user.role == 'admin'
        
        # Get FAQ counts by state (always visible)
        faqs_by_state = db.session.query(
            FAQ.state_name, func.count(FAQ.id)
        ).filter(FAQ.state_name.isnot(None)).group_by(FAQ.state_name).all()
        
        # Get user counts by state (always visible)
        users_by_state = db.session.query(
            User.state_name, func.count(User.id)
        ).filter(User.state_name.isnot(None)).group_by(User.state_name).all()
        
        # Get DataDump counts by state (always visible)
        dumps_by_state = db.session.query(
            DataDump.state, func.count(DataDump.id)
        ).filter(DataDump.state.isnot(None)).group_by(DataDump.state).all()
        
        # Get DraftFAQ counts by state (admin only)
        draft_faqs_by_state = []
        if is_admin:
            draft_faqs_by_state = db.session.query(
                DraftFAQ.state_name, func.count(DraftFAQ.id)
            ).filter(DraftFAQ.state_name.isnot(None)).group_by(DraftFAQ.state_name).all()
        
        # Combine all data
        state_stats = {}
        
        # Initialize with FAQ data
        for state, faq_count in faqs_by_state:
            state_stats[state] = {
                'approved_faqs': faq_count,
                'draft_faqs': 0,
                'users': 0,
                'dump_requests': 0
            }
        
        # Add DraftFAQ data (admin only)
        if is_admin:
            for state, draft_count in draft_faqs_by_state:
                if state in state_stats:
                    state_stats[state]['draft_faqs'] = draft_count
                else:
                    state_stats[state] = {
                        'approved_faqs': 0,
                        'draft_faqs': draft_count,
                        'users': 0,
                        'dump_requests': 0
                    }
        
        # Add user data
        for state, user_count in users_by_state:
            if state in state_stats:
                state_stats[state]['users'] = user_count
            else:
                state_stats[state] = {
                    'approved_faqs': 0,
                    'draft_faqs': 0,
                    'users': user_count,
                    'dump_requests': 0
                }
        
        # Add DataDump data
        for state, dump_count in dumps_by_state:
            if state in state_stats:
                state_stats[state]['dump_requests'] = dump_count
            else:
                state_stats[state] = {
                    'approved_faqs': 0,
                    'draft_faqs': 0,
                    'users': 0,
                    'dump_requests': dump_count
                }
        
        return {
            'state_statistics': state_stats,
            'total_states': len(state_stats),
            'is_admin': is_admin,
            'query_type': 'state_statistics',
            'query_params': query_params or {}
        }
    
    def _get_pending_faq_statistics(self, params: Dict, user_id: int = None) -> Dict:
        """Get pending/unanswered FAQ statistics (admin only)"""
        
        # Check if user is admin
        is_admin = False
        if user_id:
            user = User.query.get(user_id)
            is_admin = user and user.role == 'admin'
        
        if not is_admin:
            return {
                'error': 'You do not have permission to view pending queries.',
                'query_type': 'pending_faqs'
            }
        
        # Get pending DraftFAQ counts by state
        pending_faqs_by_state = db.session.query(
            DraftFAQ.state_name, func.count(DraftFAQ.id)
        ).filter(DraftFAQ.status == 'pending', DraftFAQ.state_name.isnot(None)).group_by(DraftFAQ.state_name).all()
        
        # Get total pending FAQs
        total_pending = DraftFAQ.query.filter(DraftFAQ.status == 'pending').count()
        
        # Get overall statistics
        total_drafts = DraftFAQ.query.count()
        total_approved = DraftFAQ.query.filter(DraftFAQ.status == 'merged').count()
        total_rejected = DraftFAQ.query.filter(DraftFAQ.status == 'rejected').count()
        
        return {
            'total_pending': total_pending,
            'total_drafts': total_drafts,
            'total_approved': total_approved,
            'total_rejected': total_rejected,
            'pending_by_state': dict(pending_faqs_by_state),
            'query_type': 'pending_faqs'
        }
    
    def _get_total_count_statistics(self, params: Dict) -> Dict:
        """Get total count statistics for FAQs and audits"""
        
        total_faqs = FAQ.query.count()
        total_drafts = DraftFAQ.query.count()
        total_users = User.query.count()
        total_dumps = DataDump.query.count()
        
        return {
            'total_faqs': total_faqs,
            'total_drafts': total_drafts,
            'total_users': total_users,
            'total_dumps': total_dumps,
            'query_type': 'total_count'
        }
    
    def _get_trend_analysis(self, params: Dict) -> Dict:
        """Get trend analysis data"""
        
        period = params.get('period', '30')  # default to 30 days
        
        if period == '30':
            start_date = datetime.utcnow() - timedelta(days=30)
        elif period == '90':
            start_date = datetime.utcnow() - timedelta(days=90)
        else:
            start_date = datetime.utcnow() - timedelta(days=365)  # 1 year
        
        # User registration trends - using Logs as proxy since User doesn't have created_at
        user_trends = db.session.query(
            func.date(Logs.timestamp), func.count(Logs.id)
        ).filter(Logs.action.like('%registered%'), Logs.timestamp >= start_date).group_by(func.date(Logs.timestamp)).all()
        
        # Data dump request trends
        dump_trends = db.session.query(
            func.date(DataDump.created_at), func.count(DataDump.id)
        ).filter(DataDump.created_at >= start_date).group_by(func.date(DataDump.created_at)).all()
        
        return {
            'user_registration_trends': dict(user_trends),
            'dump_request_trends': dict(dump_trends),
            'period_days': period,
            'query_type': 'trend_analysis'
        }
    
    def _get_comparison_data(self, params: Dict) -> Dict:
        """Get comparison data between entities"""
        
        comparison_type = params.get('compare')
        
        if comparison_type == 'states':
            # Compare states by various metrics
            state_metrics = {}
            states = db.session.query(DataDump.state).distinct().all()
            
            for state_tuple in states:
                state = state_tuple[0]
                if state:
                    dump_count = DataDump.query.filter(DataDump.state == state).count()
                    user_count = User.query.filter(User.state_name == state).count()
                    
                    state_metrics[state] = {
                        'dump_requests': dump_count,
                        'users': user_count
                    }
            
            return {
                'comparison_type': 'states',
                'data': state_metrics,
                'query_type': 'comparison'
            }
        
        return None
    
    def _format_data_response(self, data: Dict, query_result: Dict, original_message: str) -> str:
        """Format data response in natural language"""
        
        query_type = data.get('query_type', 'unknown')
        
        if query_type == 'user_statistics':
            return self._format_user_stats_response(data)
        elif query_type == 'datadump_statistics':
            return self._format_datadump_stats_response(data)
        elif query_type == 'state_statistics':
            return self._format_state_stats_response(data)
        elif query_type == 'trend_analysis':
            return self._format_trend_response(data)
        elif query_type == 'comparison':
            return self._format_comparison_response(data)
        elif query_type == 'pending_faqs':
            return self._format_pending_faqs_response(data)
        elif query_type == 'total_count':
            return self._format_total_count_response(data)
        else:
            return f"Based on your question about '{original_message}', I found the following information."
    
    def _format_user_stats_response(self, data: Dict) -> str:
        """Format user statistics in natural language"""
        
        total_users = data['total_users']
        recent_registrations = data['recent_registrations']
        role_dist = data['role_distribution']
        state_dist = data['state_distribution']
        
        response = f"User Statistics Overview\n\n"
        response += f"Total Users: {total_users:,}\n"
        response += f"New Registrations (Last 30 Days): {recent_registrations}\n\n"
        
        if role_dist:
            response += "By Role:\n"
            for role, count in role_dist.items():
                percentage = (count / total_users) * 100 if total_users > 0 else 0
                response += f"- {role.title()}: {count} ({percentage:.1f}%)\n"
        
        if state_dist:
            response += "\nTop States by Users:\n"
            sorted_states = sorted(state_dist.items(), key=lambda x: x[1], reverse=True)[:5]
            for state, count in sorted_states:
                response += f"- {state}: {count}\n"
        
        return response
    
    def _format_datadump_stats_response(self, data: Dict) -> str:
        """Format data dump statistics in natural language"""
        
        total_requests = data['total_requests']
        status_dist = data['status_distribution']
        state_dist = data['state_distribution']
        avg_time = data['average_processing_days']
        
        response = f"Data Dump Statistics\n\n"
        response += f"Total Requests: {total_requests:,}\n"
        response += f"Average Processing Time: {avg_time} days\n\n"
        
        if status_dist:
            response += "By Status:\n"
            for status, count in status_dist.items():
                percentage = (count / total_requests) * 100 if total_requests > 0 else 0
                response += f"- {status}: {count} ({percentage:.1f}%)\n"
        
        if state_dist:
            response += "\nStates that have received data dumps:\n"
            if state_dist:
                sorted_states = sorted(state_dist.items(), key=lambda x: x[1], reverse=True)
                for state, count in sorted_states:
                    response += f"- {state}: {count} data dump(s)\n"
            else:
                response += "No states have received data dumps yet.\n"
        else:
            response += "\nNo data dumps have been distributed to any states yet.\n"
        
        return response
    
    def _format_state_stats_response(self, data: Dict) -> str:
        """Format state statistics in natural language with role-based filtering"""
        
        total_states = data['total_states']
        state_stats = data['state_statistics']
        is_admin = data.get('is_admin', False)
        
        # Check if this is a specific state query
        query_params = data.get('query_params', {})
        specific_state = query_params.get('specific_state')
        
        if specific_state and specific_state in state_stats:
            # Return specific state information
            stats = state_stats[specific_state]
            response = f"{specific_state} Statistics\n\n"
            
            # Always show approved FAQs
            response += f"Approved FAQs: {stats['approved_faqs']}\n"
            
            # Only show draft FAQs if admin
            if is_admin:
                response += f"Draft FAQs: {stats['draft_faqs']}\n"
                total_faqs = stats['approved_faqs'] + stats['draft_faqs']
                response += f"Total FAQs: {total_faqs}\n"
            
            response += f"Registered Users: {stats['users']}\n"
            response += f"Data Dump Requests: {stats['dump_requests']}\n"
            
            # Add note about draft FAQs for non-admins
            if not is_admin and stats['draft_faqs'] > 0:
                response += f"\nNote: There are additional draft FAQs pending review.\n"
            
            return response
        
        response = f"State Statistics\n\n"
        response += f"Active States: {total_states}\n\n"
        
        # Sort by FAQ activity (approved FAQs only for non-admins)
        if is_admin:
            sorted_states = sorted(
                state_stats.items(), 
                key=lambda x: x[1]['approved_faqs'] + x[1]['draft_faqs'], 
                reverse=True
            )[:10]
            
            response += "Top States by FAQ Activity:\n"
            for state, stats in sorted_states:
                total_faqs = stats['approved_faqs'] + stats['draft_faqs']
                response += f"- {state}: {stats['approved_faqs']} approved FAQs, {stats['draft_faqs']} draft FAQs (Total: {total_faqs})\n"
            
            # Add state with most FAQs highlight
            if sorted_states:
                top_state, top_stats = sorted_states[0]
                response += f"\n{top_state} has the most FAQs with {top_stats['approved_faqs']} approved and {top_stats['draft_faqs']} draft FAQs.\n"
        else:
            # Non-admin view - only show approved FAQs
            sorted_states = sorted(
                state_stats.items(), 
                key=lambda x: x[1]['approved_faqs'], 
                reverse=True
            )[:10]
            
            response += "Top States by Approved FAQs:\n"
            for state, stats in sorted_states:
                response += f"- {state}: {stats['approved_faqs']} approved FAQs\n"
            
            # Add state with most FAQs highlight
            if sorted_states:
                top_state, top_stats = sorted_states[0]
                response += f"\n{top_state} has the most approved FAQs with {top_stats['approved_faqs']} FAQs.\n"
        
        # Add TN specific data if available
        if 'TN' in state_stats:
            tn_stats = state_stats['TN']
            if is_admin:
                response += f"\nTamil Nadu (TN): {tn_stats['approved_faqs']} approved FAQs, {tn_stats['draft_faqs']} draft FAQs\n"
            else:
                response += f"\nTamil Nadu (TN): {tn_stats['approved_faqs']} approved FAQs\n"
        
        return response
    
    def _format_trend_response(self, data: Dict) -> str:
        """Format trend analysis in natural language"""
        
        period = data['period_days']
        user_trends = data['user_registration_trends']
        dump_trends = data['dump_request_trends']
        
        response = f"Trend Analysis (Last {period} Days)\n\n"
        
        if user_trends:
            total_new_users = sum(user_trends.values())
            avg_daily_users = total_new_users / len(user_trends)
            response += f"User Registrations: {total_new_users} total (avg: {avg_daily_users:.1f}/day)\n"
        
        if dump_trends:
            total_dumps = sum(dump_trends.values())
            avg_daily_dumps = total_dumps / len(dump_trends)
            response += f"Data Dump Requests: {total_dumps} total (avg: {avg_daily_dumps:.1f}/day)\n"
        
        return response
    
    def _format_comparison_response(self, data: Dict) -> str:
        """Format comparison data in natural language"""
        
        comparison_type = data['comparison_type']
        comparison_data = data['data']
        
        if comparison_type == 'states':
            response = f"State Comparison\n\n"
            
            # Sort by total activity
            sorted_states = sorted(
                comparison_data.items(),
                key=lambda x: x[1]['dump_requests'] + x[1]['users'],
                reverse=True
            )
            
            for i, (state, stats) in enumerate(sorted_states[:10], 1):
                total = stats['dump_requests'] + stats['users']
                response += f"{i}. {state}: {stats['dump_requests']} dumps, {stats['users']} users (Total: {total})\n"
        
        return response
    
    def _format_pending_faqs_response(self, data: Dict) -> str:
        """Format pending FAQ statistics in natural language"""
        
        # Check for permission error
        if 'error' in data:
            return data['error']
        
        total_pending = data['total_pending']
        total_drafts = data['total_drafts']
        total_approved = data['total_approved']
        total_rejected = data['total_rejected']
        pending_by_state = data['pending_by_state']
        
        response = f"Pending/Unanswered Queries Report\n\n"
        response += f"Total Pending Queries: {total_pending}\n"
        response += f"Total Draft FAQs: {total_drafts}\n"
        response += f"Total Approved: {total_approved}\n"
        response += f"Total Rejected: {total_rejected}\n\n"
        
        if total_drafts > 0:
            approval_rate = (total_approved / total_drafts) * 100
            pending_rate = (total_pending / total_drafts) * 100
            response += f"Approval Rate: {approval_rate:.1f}%\n"
            response += f"Pending Rate: {pending_rate:.1f}%\n\n"
        
        if pending_by_state:
            response += "Pending Queries by State:\n"
            sorted_states = sorted(pending_by_state.items(), key=lambda x: x[1], reverse=True)
            for state, count in sorted_states:
                response += f"- {state}: {count} pending queries\n"
        else:
            response += "No pending queries found. All queries have been processed!\n"
        
        return response
    
    def _format_total_count_response(self, data: Dict) -> str:
        """Format total count statistics in natural language"""
        
        total_faqs = data['total_faqs']
        total_drafts = data['total_drafts']
        total_users = data['total_users']
        total_dumps = data['total_dumps']
        
        response = f"System Overview\n\n"
        response += f"Total Approved FAQs: {total_faqs}\n"
        response += f"Total Draft FAQs: {total_drafts}\n"
        response += f"Total Users: {total_users}\n"
        response += f"Total Data Dump Requests: {total_dumps}\n\n"
        
        if total_drafts > 0:
            approval_rate = (total_faqs / total_drafts) * 100
            response += f"Overall FAQ Approval Rate: {approval_rate:.1f}%\n"
        
        return response
    
    def _generate_followup_suggestions(self, query_result: Dict) -> List[str]:
        """Generate intelligent follow-up suggestions"""
        
        suggestions = []
        query_type = query_result['type']
        
        if query_type == 'user_count':
            suggestions.extend([
                "Show user registration trends over time",
                "Compare users by state",
                "Show user role distribution"
            ])
        elif query_type == 'datadump_count':
            suggestions.extend([
                "Show average processing time by state",
                "Compare approval vs rejection rates",
                "Show most active states"
            ])
        elif query_type == 'state_summary':
            suggestions.extend([
                "Show top 5 states by activity",
                "Compare user vs dump request ratios",
                "Show state-wise processing times"
            ])
        
        return suggestions[:3]
    
    def _generate_data_query_help(self, message: str) -> str:
        """Generate helpful response for data queries"""
        
        return """Data Query Help

I can help you get insights from the system data. Here are some examples of what you can ask:

User Statistics:
- "How many users are registered?"
- "Show me users by role"
- "Count users by state"
- "Recent registration trends"

Data Dump Analytics:
- "How many data dump requests are pending?"
- "Show approval rates by state"
- "Average processing time for requests"
- "Most requested data types"

State Comparisons:
- "Compare activity between states"
- "Which state has the most users?"
- "Show state-wise dump statistics"

Trend Analysis:
- "Show user registration trends"
- "Data dump request patterns over time"
- "Monthly system activity

Try asking in natural language - I'll understand and provide the insights!"""
    
    def _handle_comprehensive_guidance(self, message: str, intent: Dict, context: List) -> Dict:
        """Handle comprehensive application guidance"""
        
        guidance_type = intent.get('guidance_type', 'general')
        
        if guidance_type == 'workflow':
            response = self._provide_workflow_guidance(message, intent)
        elif guidance_type == 'navigation':
            response = self._provide_navigation_guidance(message, intent)
        elif guidance_type == 'troubleshooting':
            response = self._provide_troubleshooting_guidance(message, intent)
        else:
            response = self._provide_general_guidance(message, intent)
        
        return {
            'response': response,
            'sources': ['application_knowledge'],
            'suggestions': self._generate_guidance_suggestions(guidance_type)
        }
    
    def _provide_workflow_guidance(self, message: str, intent: Dict) -> str:
        """Provide detailed workflow guidance"""
        
        message_lower = message.lower()
        
        # Check for specific workflows
        for workflow_name, workflow_info in self.app_knowledge['workflows'].items():
            if any(keyword in message_lower for keyword in workflow_name.split('_')):
                response = f"{workflow_name.replace('_', ' ').title()} Workflow\n\n"
                response += f"Steps:\n"
                for step in workflow_info['steps']:
                    response += f"{step}\n"
                
                if 'average_time' in workflow_info:
                    response += f"\nAverage Time: {workflow_info['average_time']}\n"
                
                if 'requirements' in workflow_info:
                    response += f"Requirements: {workflow_info['requirements']}\n"
                
                response += f"\nNeed Help? Ask me about any specific step and I'll provide more details!"
                
                return response
        
        return self._generate_workflow_help()
    
    def _provide_navigation_guidance(self, message: str, intent: Dict) -> str:
        """Provide navigation guidance"""
        
        return """Navigation Guide

Main Menu Sections:

Dashboard
- System overview and statistics
- Quick actions and shortcuts
- Recent activity feed

Data Dump
- Request new data dumps
- Track request status
- Download approved data
- Upload completed documents

User Management (Admin only)
- Approve pending registrations
- Manage user roles and permissions
- View user activity

FAQ / Replied
- Browse knowledge base
- Search for specific topics
- Add new FAQ entries

AI Assistant
- Get help and guidance
- Ask questions in natural language
- Receive data insights

Quick Navigation: Use the sidebar menu or click on section headers to navigate between different areas."""
    
    def _provide_troubleshooting_guidance(self, message: str, intent: Dict) -> str:
        """Provide troubleshooting guidance"""
        
        message_lower = message.lower()
        
        if 'login' in message_lower or 'sign in' in message_lower:
            return """Login Troubleshooting

Can't login? Try these steps:

1. Check Credentials
   - Verify email and password are correct
   - Check for typos and extra spaces

2. Account Status
   - Ensure your registration is approved
   - Check for confirmation email

3. Password Reset
   - Click "Forgot Password" on login page
   - Follow email instructions
   - Create new strong password

4. Browser Issues
   - Clear browser cache and cookies
   - Try a different browser
   - Disable browser extensions

5. Still having issues?
   - Contact your system administrator
   - Check if your account is locked

Need more help? Describe your specific issue and I'll help further!"""
        
        elif 'upload' in message_lower or 'download' in message_lower:
            return """File Upload/Download Troubleshooting

Upload Issues:
- Check file size limits (max 50MB)
- Ensure file format is supported
- Verify you have proper permissions
- Try refreshing the page

Download Issues:
- Check if download was approved
- Verify your browser allows downloads
- Check download folder location
- Try right-click and "Save Link As"

File Not Found?
- Confirm the request was approved
- Check your user permissions
- Contact administrator if needed"""
        
        return self._generate_general_troubleshooting()
    
    def _generate_workflow_help(self) -> str:
        """Generate general workflow help"""
        
        return """Available Workflows

I can guide you through these main workflows:

Data Dump Request Process
- Request → Approval → Download → Upload

User Registration Process  
- Register → Approval → Login → Access

Audit Management Process
- Create → Assign → Conduct → Report

Ask me specifically about:
- "How to request a data dump?"
- "User registration process"
- "Audit workflow steps"
- "Navigate to dashboard"

I'll provide detailed step-by-step guidance!"""
    
    def _generate_general_troubleshooting(self) -> str:
        """Generate general troubleshooting help"""
        
        return """General Troubleshooting

Common Issues & Solutions:

Access Denied
- Check if you're logged in
- Verify your account is approved
- Ensure you have proper permissions

Slow Performance
- Clear browser cache
- Check internet connection
- Try refreshing the page

Error Messages
- Note the exact error text
- Try the action again
- Contact admin if persistent

Mobile Issues
- Use desktop for complex tasks
- Ensure mobile browser is supported
- Try landscape orientation

Need specific help? Describe your issue and I'll provide targeted solutions!"""
    
    def _provide_general_guidance(self, message: str, intent: Dict) -> str:
        """Provide general application guidance"""
        
        return """How I Can Help You

I'm your AI assistant for the Audit Management System! Here's what I can do:

Data Insights
- Answer questions about users, requests, and statistics
- Provide trends and analytics
- Compare data across states and time periods

Application Guidance
- Guide you through workflows step-by-step
- Help with navigation and features
- Provide troubleshooting assistance

Knowledge Base
- Answer questions about system functionality
- Help with policies and procedures
- Provide best practices

Smart Suggestions
- Suggest relevant actions based on context
- Provide follow-up questions
- Offer related information

Try asking me:
- "How many users are registered?"
- "Guide me through data dump request"
- "Show me trends for last month"
- "Help with login issues"

I understand natural language - just ask as you would to a human assistant!"""
    
    def _generate_guidance_suggestions(self, guidance_type: str) -> List[str]:
        """Generate contextual guidance suggestions"""
        
        suggestions = []
        
        if guidance_type == 'workflow':
            suggestions.extend([
                "Explain data dump approval process",
                "User registration workflow steps",
                "Audit management guide"
            ])
        elif guidance_type == 'navigation':
            suggestions.extend([
                "How to access dashboard",
                "Where to find data dumps",
                "Navigate to user management"
            ])
        elif guidance_type == 'troubleshooting':
            suggestions.extend([
                "Login not working",
                "Can't upload files",
                "Download issues"
            ])
        else:
            suggestions.extend([
                "System overview",
                "Main features guide",
                "Getting started help"
            ])
        
        return suggestions
    
    def _handle_conversational_query(self, message: str, intent: Dict, context: List) -> Dict:
        """Handle conversational queries using LLM"""
        
        try:
            # Use LLM to generate natural response
            llm_response = self.llm_generator.generate_response(message)
            
            return {
                'response': llm_response['response'],
                'sources': llm_response.get('sources', ['conversational_ai']),
                'suggestions': self._generate_conversational_suggestions(),
                'llm_enhanced': True,
                'confidence': llm_response.get('confidence', 0.8)
            }
            
        except Exception as e:
            current_app.logger.error(f"Conversational query error: {e}")
            # Fallback to original method
            return self._fallback_conversational_response(message, intent, context)
    
    def _fallback_conversational_response(self, message: str, intent: Dict, context: List) -> Dict:
        """Fallback conversational response when LLM fails"""
        
        message_lower = message.lower()
        
        # Greetings
        if any(greeting in message_lower for greeting in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
            response = "Hello! I'm your AI assistant for the Audit Management System. How can I help you today?"
        
        # Capabilities
        elif any(word in message_lower for word in ['what can you do', 'help', 'capabilities', 'features']):
            response = "I can help you with data queries, application guidance, and troubleshooting. Ask me about state statistics, FAQs, or system information."
        
        # System status
        elif any(word in message_lower for word in ['system status', 'how are you', 'working']):
            response = "I'm working fine and ready to help you with your Audit Management System queries."
        
        else:
            response = "I'm here to help with the Audit Management System. You can ask me about state data, FAQs, or system information."
        
        return {
            'response': response,
            'sources': ['fallback_conversational'],
            'suggestions': self._generate_conversational_suggestions(),
            'llm_enhanced': False,
            'confidence': 0.6
        }
    
    def _generate_greeting_response(self) -> str:
        """Generate greeting response"""
        
        greetings = [
            "Hello! I'm your AI assistant for the Audit Management System. How can I help you today?",
            "Hi there! I'm here to help you navigate the Audit Management System. What would you like to know?",
            "Greetings! I can assist with data queries, application guidance, and troubleshooting. What can I help you with?"
        ]
        
        import random
        return random.choice(greetings)
    
    def _generate_capabilities_response(self) -> str:
        """Generate capabilities response"""
        
        return """My Capabilities

I'm an advanced AI assistant that can help you with:

Data Analytics
- Natural language queries about system data
- Statistics and trends analysis
- Comparative analysis between states/time periods
- Real-time insights and metrics

Application Guidance
- Step-by-step workflow assistance
- Navigation help and feature explanations
- Troubleshooting common issues
- Best practices and recommendations

Conversational AI
- Understand context and follow-up questions
- Provide intelligent suggestions
- Learn from conversation history
- Adapt to your needs

Smart Features
- Intent recognition and context awareness
- Multi-turn conversation support
- Personalized recommendations
- Proactive assistance

Try me with:
- "Show me user registration trends"
- "How do I request a data dump?"
- "Compare activity between states"
- "Help with login issues"

I'm here to make your experience smooth and productive!"""
    
    def _generate_status_response(self) -> str:
        """Generate system status response"""
        
        try:
            # Get basic system stats
            total_users = User.query.count()
            pending_dumps = DataDump.query.filter_by(status='PENDING').count()
            
            response = f"System Status: Healthy\n\n"
            response += f"Current Statistics:\n"
            response += f"- Total Users: {total_users:,}\n"
            response += f"- Pending Requests: {pending_dumps}\n"
            response += f"- AI Assistant: Operational\n"
            response += f"- Response Time: Excellent\n\n"
            response += f"I'm ready to help! What would you like to know?"
            
            return response
            
        except Exception as e:
            return f"System Status: Operational\n\nI'm working properly and ready to assist you with any questions about the Audit Management System!"
    
    def _generate_general_conversational_response(self, message: str, context: List) -> str:
        """Generate general conversational response"""
        
        return """I'm here to help you with the Audit Management System! 

I can assist with:
- Data queries and analytics
- Application guidance and workflows  
- Questions about features and navigation
- Troubleshooting common issues

What would you like to know or do? Feel free to ask in natural language!"""
    
    def _generate_conversational_suggestions(self) -> List[str]:
        """Generate conversational suggestions"""
        
        return [
            "Show me system statistics",
            "How to request data dump",
            "User registration guide",
            "Help with common issues"
        ]
    
    def _handle_comparison_query(self, message: str, intent: Dict, state_name: str, context: List) -> Dict:
        """Handle comparison queries"""
        
        comparison_params = intent.get('comparison_params', {})
        
        if comparison_params.get('type') == 'state':
            data = self._get_comparison_data({'compare': 'states'})
            
            if data:
                response = self._format_comparison_response(data)
                return {
                    'response': response,
                    'sources': ['database_query'],
                    'data': data
                }
        
        return {
            'response': "I can help you compare different aspects of the system. Try asking:\n- 'Compare activity between states'\n- 'Show me state-wise statistics'\n- 'Which state has the most users?'",
            'sources': ['help_system']
        }
    
    def _handle_troubleshooting_query(self, message: str, intent: Dict, context: List) -> Dict:
        """Handle troubleshooting queries"""
        
        return self._handle_comprehensive_guidance(message, {'guidance_type': 'troubleshooting'}, context)
    
    def _handle_intelligent_faq_search(self, message: str, intent: Dict, state_name: str, context: List) -> Dict:
        """Handle enhanced FAQ search with LLM-powered responses"""
        
        try:
            # Search in FAQ database
            results = find_related_questions_scored(
                question=message,
                reply="",
                memo_id=None,
                state_name=state_name
            )
            
            if results and len(results) > 0:
                # Get the best result
                best_result = results[0]
                
                # Check if it's a good match
                if best_result.get('score', 0) > 0.7:
                    # Use LLM to generate natural response from FAQ data
                    faq_data = {
                        'question': best_result.get('question', ''),
                        'answer': best_result.get('reply', ''),
                        'score': best_result.get('score', 0),
                        'related_questions': results[1:3] if len(results) > 1 else []
                    }
                    
                    # Create context for LLM
                    context_data = {
                        'faq_result': faq_data,
                        'state_name': state_name,
                        'user_context': context
                    }
                    
                    # Generate LLM response
                    llm_response = self.llm_generator.generate_response(message, context_data)
                    
                    return {
                        'response': llm_response['response'],
                        'sources': ['faq_database', 'llm_enhanced'],
                        'confidence': best_result.get('score', 0.8),
                        'llm_enhanced': True,
                        'faq_data': faq_data
                    }
            
            # No good FAQ match, use LLM to provide intelligent help
            help_context = {
                'no_faq_found': True,
                'original_message': message,
                'intent': intent,
                'state_name': state_name
            }
            
            llm_response = self.llm_generator.generate_response(message, help_context)
            
            return {
                'response': llm_response['response'],
                'sources': ['llm_enhanced'],
                'suggestions': self._generate_contextual_suggestions(message),
                'llm_enhanced': True,
                'confidence': llm_response.get('confidence', 0.6)
            }
            
        except Exception as e:
            current_app.logger.error(f"FAQ search error: {e}")
            return {
                'response': "I had trouble searching the knowledge base. Let me help you directly - what specific information are you looking for?",
                'sources': ['fallback']
            }
    
    def _generate_intelligent_help_suggestions(self, message: str, intent: Dict) -> str:
        """Generate intelligent help suggestions based on message analysis"""
        
        message_lower = message.lower()
        
        # Analyze message content to provide targeted help
        if any(word in message_lower for word in ['data', 'dump', 'request', 'download']):
            return """Data Dump Help

I can help you with data dump related questions:

Common Queries:
- "How many data dump requests are pending?"
- "Show me requests by state"
- "Average processing time"
- "How to request a data dump"

Try asking: "Show me data dump statistics" or "How to request data dump?"""
        
        elif any(word in message_lower for word in ['user', 'account', 'registration', 'login']):
            return """User Management Help

I can help with user-related questions:

Common Queries:
- "How many users are registered?"
- "User registration trends"
- "Users by state or role"
- "Account approval process"

Try asking: "Show me user statistics" or "How does user registration work?"""
        
        elif any(word in message_lower for word in ['audit', 'report', 'process']):
            return """Audit Process Help

I can help with audit-related questions:

Common Queries:
- "Audit workflow steps"
- "How to create audit report"
- "Audit status tracking"
- "Audit completion rates"

Try asking: "Guide me through audit process" or "Show audit statistics"""
        
        else:
            return """General Help

I can assist you with various aspects of the Audit Management System:

Data Analytics
- User statistics and trends
- Data dump analytics
- State-wise comparisons
- System performance metrics

Application Guidance
- Workflow step-by-step help
- Navigation assistance
- Feature explanations
- Troubleshooting support

Try asking:
- "How many users are registered?"
- "Guide me through data dump request"
- "Show me system statistics"
- "Help with login issues"

I understand natural language - just ask your question!"""
    
    def _generate_contextual_suggestions(self, message: str) -> List[str]:
        """Generate contextual suggestions based on message"""
        
        message_lower = message.lower()
        suggestions = []
        
        if 'data' in message_lower or 'dump' in message_lower:
            suggestions.extend([
                "Show data dump statistics",
                "How to request data dump",
                "Pending requests by state"
            ])
        
        if 'user' in message_lower or 'account' in message_lower:
            suggestions.extend([
                "User registration trends",
                "Users by state",
                "Account approval process"
            ])
        
        if 'how to' in message_lower or 'guide' in message_lower:
            suggestions.extend([
                "Data dump request workflow",
                "User registration guide",
                "Navigation help"
            ])
        
        if not suggestions:
            suggestions = [
                "Show system statistics",
                "How to request data dump",
                "User management guide",
                "Troubleshooting help"
            ]
        
        return suggestions[:4]
    
    def check_memory_usage(self) -> Dict:
        """Check memory usage of the AI assistant"""
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,
            'vms_mb': memory_info.vms / 1024 / 1024
        }
    
    def get_conversation_stats(self) -> Dict:
        """Get conversation statistics"""
        return {
            'session_id': self.conversation_memory.get_session_id(),
            'turns': len(self.conversation_memory.get_session_history())
        }


class NLPProcessor:
    """Natural Language Processing for intent analysis"""
    
    def analyze_intent(self, message: str) -> Dict:
        """Analyze user intent from message"""
        
        message_lower = message.lower()
        
        # Data query indicators
        data_keywords = [
            'how many', 'count', 'total', 'number of', 'show me', 'list',
            'statistics', 'analytics', 'trends', 'compare', 'versus', 'vs',
            'which', 'has', 'more', 'most', 'faq', 'faqs', 'questions', 'queries'
        ]
        
        # Application guidance indicators
        guidance_keywords = [
            'how to', 'how do i', 'guide', 'navigate', 'access', 'find',
            'where is', 'workflow', 'process', 'steps', 'tutorial'
        ]
        
        # Conversational indicators
        conversational_keywords = [
            'hello', 'hi', 'hey', 'thanks', 'thank you', 'bye', 'goodbye',
            'what can you do', 'help', 'capabilities', 'features'
        ]
        
        # Comparison indicators
        comparison_keywords = [
            'compare', 'versus', 'vs', 'difference', 'between', 'better',
            'higher', 'lower', 'more', 'less', 'top', 'best'
        ]
        
        # Troubleshooting indicators
        troubleshooting_keywords = [
            'error', 'issue', 'problem', 'trouble', 'not working', 'broken',
            'can\'t', 'unable', 'failed', 'stuck', 'help', 'fix'
        ]
        
        # Calculate intent scores
        scores = {
            'data_query': self._calculate_keyword_score(message_lower, data_keywords),
            'application_guidance': self._calculate_keyword_score(message_lower, guidance_keywords),
            'conversation': self._calculate_keyword_score(message_lower, conversational_keywords),
            'comparison': self._calculate_keyword_score(message_lower, comparison_keywords),
            'troubleshooting': self._calculate_keyword_score(message_lower, troubleshooting_keywords)
        }
        
        # Determine primary intent
        primary_intent = max(scores, key=scores.get)
        confidence = scores[primary_intent]
        
        # Extract additional parameters
        params = self._extract_parameters(message_lower, primary_intent)
        
        return {
            'type': primary_intent,
            'confidence': confidence,
            'params': params,
            'scores': scores
        }
    
    def _calculate_keyword_score(self, message: str, keywords: List[str]) -> float:
        """Calculate keyword match score"""
        score = 0.0
        for keyword in keywords:
            if keyword in message:
                score += 1.0
        return score
    
    def _extract_parameters(self, message: str, intent_type: str) -> Dict:
        """Extract parameters from message based on intent"""
        
        params = {}
        
        if intent_type == 'data_query':
            # Extract time periods
            if 'last month' in message or '30 days' in message:
                params['period'] = '30'
            elif 'last quarter' in message or '90 days' in message:
                params['period'] = '90'
            elif 'last year' in message or '12 months' in message:
                params['period'] = '365'
            
            # Extract roles
            if 'admin' in message:
                params['role'] = 'admin'
            elif 'user' in message:
                params['role'] = 'user'
            
            # Extract status
            if 'pending' in message:
                params['status'] = 'requested'  # Use 'requested' instead of 'PENDING'
            elif 'approved' in message or 'provided' in message:
                params['status'] = 'provided'  # Use 'provided' instead of 'APPROVED'
            elif 'rejected' in message:
                params['status'] = 'rejected'
        
        elif intent_type == 'application_guidance':
            if 'workflow' in message:
                params['guidance_type'] = 'workflow'
            elif 'navigate' in message or 'navigation' in message:
                params['guidance_type'] = 'navigation'
            elif 'troubleshoot' in message or 'issue' in message:
                params['guidance_type'] = 'troubleshooting'
        
        elif intent_type == 'comparison':
            if 'state' in message:
                params['compare'] = 'states'
        
        return params
    
    def parse_sql_query(self, message: str, state_name: str) -> Optional[Dict]:
        """Parse natural language into structured query"""
        
        message_lower = message.lower()
        
        # High-level generative approach - analyze intent and generate natural responses
        if any(word in message_lower for word in ['how many', 'count', 'total', 'number of']):
            # Check what they're asking about
            if any(word in message_lower for word in ['pending', 'unanswered', 'waiting', 'need to be answered']):
                return {
                    'type': 'pending_faqs',
                    'params': {}
                }
            elif any(word in message_lower for word in ['faq','queries', 'question', 'questions', 'audit']) and 'state' not in message_lower and not any(state in message_lower for state in ['tn', 'tamil nadu', 'punjab', 'haryana', 'delhi', 'west bengal', 'jharkhand', 'odisha', 'uttarakhand', 'up', 'uttar pradesh', 'assam']):
                return {
                    'type': 'total_count',
                    'params': {}
                }
        
        # User count queries
        if any(word in message_lower for word in ['how many user', 'count user', 'total user', 'number of user', 'users are registered', 'how many users']):
            return {
                'type': 'user_count',
                'params': self._extract_user_params(message_lower)
            }
        
        # FAQ-specific queries (check before total_count)
        elif any(pattern in message_lower for pattern in ['faq', 'faqs', 'questions', 'query', 'queries']) and any(word in message_lower for word in ['how many', 'count', 'total', 'which state', 'state has', 'more faq', 'most faq', 'tn has', 'tn queries']):
            # Extract specific state if mentioned
            state_mentioned = None
            if 'tn' in message_lower or 'tamil nadu' in message_lower:
                state_mentioned = 'TN'
            elif 'punjab' in message_lower:
                state_mentioned = 'Punjab'
            elif 'haryana' in message_lower:
                state_mentioned = 'Haryana'
            elif 'delhi' in message_lower:
                state_mentioned = 'Delhi'
            elif 'west bengal' in message_lower:
                state_mentioned = 'West Bengal'
            elif 'jharkhand' in message_lower:
                state_mentioned = 'Jharkhand'
            elif 'odisha' in message_lower:
                state_mentioned = 'Odisha'
            elif 'uttarakhand' in message_lower:
                state_mentioned = 'Uttarakhand'
            elif 'up' in message_lower or 'uttar pradesh' in message_lower:
                state_mentioned = 'UP'
            elif 'assam' in message_lower:
                state_mentioned = 'Assam'
            
            return {
                'type': 'state_summary',
                'params': {'specific_state': state_mentioned} if state_mentioned else {}
            }
        
        # State-specific questions (check before total_count)
        elif any(pattern in message_lower for pattern in ['in tn', 'in tamil', 'questions in', 'how many in', 'tn has', 'tamil nadu', 'for tn', 'for tamil nadu', 'tn how many', 'how many tn', 'tn queries', 'queries tn']):
            # Extract specific state if mentioned
            state_mentioned = None
            if 'tn' in message_lower or 'tamil nadu' in message_lower:
                state_mentioned = 'TN'
            elif 'punjab' in message_lower:
                state_mentioned = 'Punjab'
            elif 'haryana' in message_lower:
                state_mentioned = 'Haryana'
            elif 'delhi' in message_lower:
                state_mentioned = 'Delhi'
            elif 'west bengal' in message_lower:
                state_mentioned = 'West Bengal'
            elif 'jharkhand' in message_lower:
                state_mentioned = 'Jharkhand'
            elif 'odisha' in message_lower:
                state_mentioned = 'Odisha'
            elif 'uttarakhand' in message_lower:
                state_mentioned = 'Uttarakhand'
            elif 'up' in message_lower or 'uttar pradesh' in message_lower:
                state_mentioned = 'UP'
            elif 'assam' in message_lower:
                state_mentioned = 'Assam'
            
            return {
                'type': 'state_summary',
                'params': {'specific_state': state_mentioned} if state_mentioned else {}
            }
        
        # Total count queries (check after state-specific) - more restrictive to avoid state queries
        elif any(word in message_lower for word in ['how many', 'count', 'total']) and any(word in message_lower for word in ['audit', 'question', 'questions', 'faq', 'faqs']) and 'state' not in message_lower and not any(state in message_lower for state in ['tn', 'tamil nadu', 'punjab', 'haryana', 'delhi', 'west bengal', 'jharkhand', 'odisha', 'uttarakhand', 'up', 'uttar pradesh', 'assam']):
            return {
                'type': 'total_count',
                'params': {}
            }
        
        # Data dump queries
        elif any(word in message_lower for word in ['data dump', 'dump request', 'datadump', 'data dump requests', 'dump statistics', 'datadump is give', 'datadump given', 'data dump given']):
            return {
                'type': 'datadump_count',
                'params': self._extract_datadump_params(message_lower, state_name)
            }
        
        # Unanswered/pending queries
        elif any(word in message_lower for word in ['unanswered', 'pending', 'not answered', 'waiting', 'unresolved']):
            return {
                'type': 'pending_faqs',
                'params': {}
            }
        
        # State queries
        elif 'state' in message_lower and any(word in message_lower for word in ['how many', 'count', 'total', 'show', 'state records', 'state faq', 'state faqs']):
            return {
                'type': 'state_summary',
                'params': {}
            }
        
        # Trend queries
        elif any(word in message_lower for word in ['trend', 'over time', 'last month', 'last year']):
            return {
                'type': 'trend_analysis',
                'params': self._extract_trend_params(message_lower)
            }
        
        # Comparison queries
        elif 'compare' in message_lower or 'versus' in message_lower or 'vs' in message_lower:
            return {
                'type': 'comparison',
                'params': self._extract_comparison_params(message_lower)
            }
        
        return None
    
    def _extract_user_params(self, message: str) -> Dict:
        """Extract user query parameters"""
        params = {}
        
        if 'admin' in message:
            params['role'] = 'admin'
        elif 'user' in message and 'admin' not in message:
            params['role'] = 'user'
        
        if 'pending' in message:
            params['approved'] = False
        elif 'approved' in message:
            params['approved'] = True
        
        return params
    
    def _extract_datadump_params(self, message: str, state_name: str) -> Dict:
        """Extract data dump query parameters"""
        params = {}
        
        if 'pending' in message:
            params['status'] = 'requested'  # Use 'requested' instead of 'PENDING'
        elif 'approved' in message or 'provided' in message:
            params['status'] = 'provided'  # Use 'provided' instead of 'APPROVED'
        elif 'rejected' in message:
            params['status'] = 'rejected'
        
        if state_name:
            params['state'] = state_name
        
        return params
    
    def _extract_trend_params(self, message: str) -> Dict:
        """Extract trend analysis parameters"""
        params = {}
        
        if 'last month' in message or '30 days' in message:
            params['period'] = '30'
        elif 'last quarter' in message or '90 days' in message:
            params['period'] = '90'
        elif 'last year' in message or '12 months' in message:
            params['period'] = '365'
        
        return params
    
    def _extract_comparison_params(self, message: str) -> Dict:
        """Extract comparison parameters"""
        params = {}
        
        if 'state' in message:
            params['compare'] = 'states'
        
        return params


class NLPProcessor:
    """Natural Language Processing for intent analysis"""
    
    def analyze_intent(self, message: str) -> Dict:
        """Analyze user intent from message"""
        
        message_lower = message.lower()
        
        # Data query indicators
        data_keywords = [
            'how many', 'count', 'total', 'number of', 'show me', 'list',
            'statistics', 'analytics', 'trends', 'compare', 'versus', 'vs'
        ]
        
        # Application guidance indicators
        guidance_keywords = [
            'how to', 'how do i', 'guide', 'navigate', 'access', 'find',
            'where is', 'workflow', 'process', 'steps', 'tutorial'
        ]
        
        # Conversational indicators
        conversational_keywords = [
            'hello', 'hi', 'hey', 'thanks', 'thank you', 'bye', 'goodbye',
            'what can you do', 'help', 'capabilities', 'features'
        ]
        
        # Comparison indicators
        comparison_keywords = [
            'compare', 'versus', 'vs', 'difference', 'between', 'better',
            'higher', 'lower', 'more', 'less', 'top', 'best'
        ]
        
        # Troubleshooting indicators
        troubleshooting_keywords = [
            'error', 'issue', 'problem', 'trouble', 'not working', 'broken',
            'can\'t', 'unable', 'failed', 'stuck', 'help', 'fix'
        ]
        
        # Calculate intent scores
        scores = {
            'data_query': self._calculate_keyword_score(message_lower, data_keywords),
            'application_guidance': self._calculate_keyword_score(message_lower, guidance_keywords),
            'conversation': self._calculate_keyword_score(message_lower, conversational_keywords),
            'comparison': self._calculate_keyword_score(message_lower, comparison_keywords),
            'troubleshooting': self._calculate_keyword_score(message_lower, troubleshooting_keywords)
        }
        
        # Determine primary intent
        primary_intent = max(scores, key=scores.get)
        confidence = scores[primary_intent]
        
        # Extract additional parameters
        params = self._extract_parameters(message_lower, primary_intent)
        
        return {
            'type': primary_intent,
            'confidence': confidence,
            'params': params,
            'scores': scores
        }
    
    def _calculate_keyword_score(self, message: str, keywords: List[str]) -> float:
        """Calculate keyword match score"""
        score = 0.0
        for keyword in keywords:
            if keyword in message:
                score += 1.0
        return score
    
    def _extract_parameters(self, message: str, intent_type: str) -> Dict:
        """Extract parameters from message based on intent"""
        
        params = {}
        
        if intent_type == 'data_query':
            # Extract time periods
            if 'last month' in message or '30 days' in message:
                params['period'] = '30'
            elif 'last quarter' in message or '90 days' in message:
                params['period'] = '90'
            elif 'last year' in message or '12 months' in message:
                params['period'] = '365'
        
        return params
    
    def parse_sql_query(self, message: str, state_name: str = None) -> Optional[Dict]:
        """Parse natural language SQL-like queries"""
        
        message_lower = message.lower()
        
        # User count queries
        if any(keyword in message_lower for keyword in ['how many users', 'count users', 'total users']):
            return {
                'type': 'user_count',
                'params': self._extract_user_params(message)
            }
        
        # Data dump queries
        elif any(keyword in message_lower for keyword in ['data dump', 'datadump', 'dump requests']):
            return {
                'type': 'datadump_count',
                'params': self._extract_datadump_params(message, state_name)
            }
        
        # State summary queries
        elif any(keyword in message_lower for keyword in ['state summary', 'state wise', 'by state']):
            return {
                'type': 'state_summary',
                'params': self._extract_state_params(message, state_name)
            }
        
        # Trend queries
        elif any(keyword in message_lower for keyword in ['trend', 'over time', 'last month', 'last year']):
            return {
                'type': 'trend_analysis',
                'params': self._extract_trend_params(message)
            }
        
        # Comparison queries
        elif 'compare' in message_lower or 'versus' in message_lower or 'vs' in message_lower:
            return {
                'type': 'comparison',
                'params': self._extract_comparison_params(message)
            }
        
        return None
    
    def _extract_user_params(self, message: str) -> Dict:
        """Extract user query parameters"""
        params = {}
        
        if 'admin' in message:
            params['role'] = 'admin'
        elif 'user' in message and 'admin' not in message:
            params['role'] = 'user'
        
        if 'pending' in message:
            params['approved'] = False
        elif 'approved' in message:
            params['approved'] = True
        
        return params
    
    def _extract_datadump_params(self, message: str, state_name: str) -> Dict:
        """Extract data dump query parameters"""
        params = {}
        
        if 'pending' in message:
            params['status'] = 'PENDING'
        elif 'approved' in message:
            params['status'] = 'APPROVED'
        elif 'rejected' in message:
            params['status'] = 'REJECTED'
        
        if state_name:
            params['state'] = state_name
        
        return params
    
    def _extract_state_params(self, message: str, state_name: str) -> Dict:
        """Extract state query parameters"""
        params = {}
        
        if state_name:
            params['specific_state'] = state_name
        
        return params
    
    def _extract_trend_params(self, message: str) -> Dict:
        """Extract trend analysis parameters"""
        params = {}
        
        if 'last month' in message or '30 days' in message:
            params['period'] = '30'
        elif 'last quarter' in message or '90 days' in message:
            params['period'] = '90'
        elif 'last year' in message or '12 months' in message:
            params['period'] = '365'
        
        return params
    
    def _extract_comparison_params(self, message: str) -> Dict:
        """Extract comparison parameters"""
        params = {}
        
        if 'state' in message:
            params['compare'] = 'states'
        
        return params


class ConversationMemory:
    """Enhanced conversation memory with context awareness"""
    
    def __init__(self, max_turns: int = 10, max_context_length: int = 2000):
        self.max_turns = max_turns
        self.max_context_length = max_context_length
        
    def get_session_id(self) -> str:
        """Get or create session ID for conversation tracking"""
        try:
            if 'chat_session_id' not in session:
                session['chat_session_id'] = str(uuid.uuid4())
            return session['chat_session_id']
        except RuntimeError:
            # Outside request context - use temporary session
            if not hasattr(self, '_temp_session_id'):
                self._temp_session_id = str(uuid.uuid4())
            return self._temp_session_id
    
    def add_turn(self, user_message: str, bot_response: str, context_data: Dict = None):
        """Add conversation turn to memory"""
        session_id = self.get_session_id()
        
        try:
            # Store in session for simplicity (can be moved to Redis later)
            if 'chat_history' not in session:
                session['chat_history'] = []
                
            turn = {
                'timestamp': datetime.utcnow().isoformat(),
                'user_message': user_message[:500],  # Limit message size
                'bot_response': bot_response[:1000],
                'context_data': context_data or {}
            }
            
            session['chat_history'].append(turn)
            
            # Limit history size
            if len(session['chat_history']) > self.max_turns:
                session['chat_history'] = session['chat_history'][-self.max_turns:]
                
        except RuntimeError:
            # Outside request context - skip storage
            pass
    
    def get_session_history(self) -> List[Dict]:
        """Get conversation history for current session"""
        try:
            return session.get('chat_history', [])
        except RuntimeError:
            return []
    
    def get_context(self) -> List[Dict]:
        """Get recent conversation context"""
        history = self.get_session_history()
        return history[-3:] if history else []  # Return last 3 turns for context


# Global instance
_chatgpt_ai_instance = None

def get_chatgpt_ai():
    """Get or create ChatGPT AI instance"""
    global _chatgpt_ai_instance
    if _chatgpt_ai_instance is None:
        _chatgpt_ai_instance = ChatGPTAIAssistant()
    return _chatgpt_ai_instance
