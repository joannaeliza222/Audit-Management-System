"""
Enhanced Query Tracking Service for AMS
Provides advanced query management, AI-powered analysis, and intelligent tracking
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd
from flask import current_app
from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.dialects.postgresql import array

from app import db
from app.models import FAQ, User, Logs
from app.audit_models import AuditQuery, AuditQueryStatus, Commitment, CommitmentStatus, QueryVersion
from app.utils.embeddings import get_bert_embeddings, normalize, find_related_questions_scored


class QueryCategory(Enum):
    FINANCIAL = 'financial'
    COMPLIANCE = 'compliance'
    OPERATIONAL = 'operational'
    TECHNICAL = 'technical'
    POLICY = 'policy'
    HUMAN_RESOURCES = 'human_resources'
    LEGAL = 'legal'
    PROCUREMENT = 'procurement'


class QueryComplexity(Enum):
    SIMPLE = 'simple'
    MODERATE = 'moderate'
    COMPLEX = 'complex'
    CRITICAL = 'critical'


class UrgencyLevel(Enum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


@dataclass
class QueryAnalysis:
    """Query analysis results"""
    query_id: int
    category: QueryCategory
    complexity: QueryComplexity
    urgency: UrgencyLevel
    confidence_score: float
    similar_queries: List[Dict]
    suggested_responses: List[Dict]
    detected_commitments: List[Dict]
    processing_time_ms: float
    model_version: str


@dataclass
class CommitmentAnalysis:
    """Commitment analysis results"""
    commitment_text: str
    category: str
    priority: str
    estimated_completion: Optional[datetime]
    confidence: float
    risk_level: str
    responsible_party: Optional[str]
    verification_method: str


class EnhancedQueryTracker:
    """Enhanced query tracking service with AI-powered analysis"""
    
    def __init__(self):
        self.embedding_model = None
        self.llm_service = None
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour
        
    def _get_embedding_model(self):
        """Lazy loading of embedding model"""
        if self.embedding_model is None:
            from app.utils.embeddings import _load_embedding_model
            self.embedding_model = _load_embedding_model()
        return self.embedding_model
    
    def _cache_key(self, prefix: str, *args) -> str:
        """Generate cache key"""
        key_parts = [prefix] + [str(arg) for arg in args]
        return "_".join(key_parts)
    
    def _get_from_cache(self, key: str):
        """Get value from cache"""
        if key in self.cache:
            cached_data, timestamp = self.cache[key]
            if datetime.utcnow().timestamp() - timestamp < self.cache_ttl:
                return cached_data
            else:
                del self.cache[key]
        return None
    
    def _set_cache(self, key: str, value):
        """Set value in cache"""
        self.cache[key] = (value, datetime.utcnow().timestamp())
    
    def analyze_query(self, query_text: str, state_name: str = None) -> QueryAnalysis:
        """
        Analyze a query using AI models
        
        Args:
            query_text: The query text to analyze
            state_name: Optional state name for context
            
        Returns:
            QueryAnalysis object with comprehensive analysis
        """
        start_time = datetime.utcnow()
        
        # Check cache first
        cache_key = self._cache_key("query_analysis", query_text, state_name or "")
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # Generate embedding
        embedding = get_bert_embeddings([query_text])[0]
        
        # Find similar queries
        similar_queries = self._find_similar_queries(query_text, embedding, state_name)
        
        # Generate suggested responses
        suggested_responses = self._generate_response_suggestions(similar_queries)
        
        # Detect commitments
        detected_commitments = self._detect_commitments(query_text)
        
        # Classify query
        category = self._classify_query_category(query_text, similar_queries)
        complexity = self._assess_query_complexity(query_text, similar_queries)
        urgency = self._assess_urgency_level(query_text, detected_commitments)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            similar_queries, suggested_responses, detected_commitments
        )
        
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        analysis = QueryAnalysis(
            query_id=0,  # Will be set when query is created
            category=category,
            complexity=complexity,
            urgency=urgency,
            confidence_score=confidence_score,
            similar_queries=similar_queries,
            suggested_responses=suggested_responses,
            detected_commitments=detected_commitments,
            processing_time_ms=processing_time,
            model_version="v1.0"
        )
        
        # Cache the result
        self._set_cache(cache_key, analysis)
        
        return analysis
    
    def _find_similar_queries(self, query_text: str, embedding: np.ndarray, 
                            state_name: str = None, limit: int = 10) -> List[Dict]:
        """Find similar queries using vector search"""
        try:
            # Search in FAQ database
            faq_similar = find_related_questions_scored(
                query_text, 
                threshold=0.7, 
                limit=limit//2,
                state_name=state_name
            )
            
            # Search in audit queries
            audit_similar = self._search_audit_queries(embedding, state_name, limit//2)
            
            # Combine and rank results
            all_similar = faq_similar + audit_similar
            all_similar.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
            
            return all_similar[:limit]
            
        except Exception as e:
            current_app.logger.error(f"Error finding similar queries: {e}")
            return []
    
    def _search_audit_queries(self, embedding: np.ndarray, state_name: str = None, 
                           limit: int = 5) -> List[Dict]:
        """Search audit queries using vector similarity"""
        try:
            from app.utils.vector_support import vector_similarity_search
            
            # Build query
            query = AuditQuery.query
            
            if state_name:
                query = query.filter(AuditQuery.state_name == state_name)
            
            # Get recent queries with responses
            recent_queries = query.filter(
                AuditQuery.status.in_([AuditQueryStatus.responded, AuditQueryStatus.closed])
            ).filter(
                AuditQuery.response_provided.isnot(None)
            ).limit(100).all()
            
            # Calculate similarities
            similar_queries = []
            for audit_query in recent_queries:
                if audit_query.embedding:
                    query_embedding = np.frombuffer(audit_query.embedding, dtype=np.float32)
                    similarity = np.dot(embedding, query_embedding) / (
                        np.linalg.norm(embedding) * np.linalg.norm(query_embedding)
                    )
                    
                    if similarity > 0.7:
                        similar_queries.append({
                            'id': audit_query.id,
                            'query_id': audit_query.query_id,
                            'query_text': audit_query.query_description,
                            'response': audit_query.response_provided,
                            'state_name': audit_query.state_name,
                            'status': audit_query.status.value,
                            'date_received': audit_query.date_received.isoformat(),
                            'similarity_score': float(similarity),
                            'source': 'audit_query'
                        })
            
            # Sort by similarity and return top results
            similar_queries.sort(key=lambda x: x['similarity_score'], reverse=True)
            return similar_queries[:limit]
            
        except Exception as e:
            current_app.logger.error(f"Error searching audit queries: {e}")
            return []
    
    def _generate_response_suggestions(self, similar_queries: List[Dict]) -> List[Dict]:
        """Generate response suggestions based on similar queries"""
        suggestions = []
        
        for similar in similar_queries[:5]:  # Top 5 similar queries
            if similar.get('response') and len(similar['response']) > 50:
                confidence = similar.get('similarity_score', 0) * 0.9  # Adjust confidence
                
                suggestion = {
                    'response_text': similar['response'],
                    'confidence': confidence,
                    'source_query_id': similar.get('query_id'),
                    'source_type': similar.get('source', 'unknown'),
                    'state_name': similar.get('state_name'),
                    'date_used': similar.get('date_received')
                }
                suggestions.append(suggestion)
        
        return suggestions
    
    def _detect_commitments(self, query_text: str) -> List[CommitmentAnalysis]:
        """Detect commitments in query text using pattern matching"""
        commitment_patterns = [
            r"will be (?:rectified|fixed|resolved|implemented|addressed)",
            r"will be (?:available|ready|deployed|launched)",
            r"planned for (?:the )?(?:next|upcoming|future)",
            r"to be (?:completed|finished|done)",
            r"future (?:release|version|update|enhancement)",
            r"under (?:development|consideration|review)",
            r"will (?:consider|evaluate|assess)",
            r"target (?:date|completion|deadline)",
            r"expected by",
            r"estimated completion"
        ]
        
        detected_commitments = []
        
        import re
        for pattern in commitment_patterns:
            matches = re.finditer(pattern, query_text, re.IGNORECASE)
            for match in matches:
                commitment_text = match.group(0)
                
                # Extract context around the match
                start = max(0, match.start() - 100)
                end = min(len(query_text), match.end() + 100)
                context = query_text[start:end].strip()
                
                # Analyze commitment
                analysis = self._analyze_commitment_text(commitment_text, context)
                detected_commitments.append(analysis)
        
        return detected_commitments
    
    def _analyze_commitment_text(self, commitment_text: str, context: str) -> CommitmentAnalysis:
        """Analyze commitment text and extract details"""
        # Determine category
        category = self._classify_commitment_category(commitment_text)
        
        # Determine priority based on keywords
        priority = self._assess_commitment_priority(commitment_text)
        
        # Extract date information
        estimated_completion = self._extract_date_from_commitment(commitment_text)
        
        # Assess risk level
        risk_level = self._assess_commitment_risk(commitment_text, context)
        
        # Determine verification method
        verification_method = self._suggest_verification_method(category)
        
        return CommitmentAnalysis(
            commitment_text=commitment_text,
            category=category,
            priority=priority,
            estimated_completion=estimated_completion,
            confidence=0.75,  # Base confidence for pattern-based detection
            risk_level=risk_level,
            responsible_party=None,  # Will be determined during query assignment
            verification_method=verification_method
        )
    
    def _classify_commitment_category(self, commitment_text: str) -> str:
        """Classify commitment category based on keywords"""
        categories = {
            'rectification': ['rectifi', 'fix', 'resolv', 'correct'],
            'implementation': ['implement', 'deploy', 'launch', 'rollout'],
            'policy_change': ['policy', 'procedure', 'guideline', 'rule'],
            'system_enhancement': ['enhance', 'improve', 'upgrade', 'feature'],
            'investigation': ['investigat', 'review', 'examine', 'study'],
            'procurement': ['procure', 'purchase', 'acquire', 'buy']
        }
        
        commitment_lower = commitment_text.lower()
        
        for category, keywords in categories.items():
            if any(keyword in commitment_lower for keyword in keywords):
                return category
        
        return 'general'
    
    def _assess_commitment_priority(self, commitment_text: str) -> str:
        """Assess commitment priority based on urgency indicators"""
        high_priority_keywords = ['urgent', 'critical', 'immediate', 'asap', 'emergency']
        medium_priority_keywords = ['soon', 'shortly', 'quickly', 'promptly']
        
        commitment_lower = commitment_text.lower()
        
        if any(keyword in commitment_lower for keyword in high_priority_keywords):
            return 'high'
        elif any(keyword in commitment_lower for keyword in medium_priority_keywords):
            return 'medium'
        else:
            return 'low'
    
    def _extract_date_from_commitment(self, commitment_text: str) -> Optional[datetime]:
        """Extract date information from commitment text"""
        import re
        from dateutil.parser import parse
        
        # Date patterns
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{1,2}/\d{1,2}/\d{4}',  # MM/DD/YYYY
            r'\d{1,2}-\d{1,2}-\d{4}',  # MM-DD-YYYY
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2},? \d{4}',  # Month DD, YYYY
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, commitment_text, re.IGNORECASE)
            if matches:
                try:
                    return parse(matches[0])
                except (ValueError, TypeError):
                    continue
        
        # Relative date patterns
        if 'next month' in commitment_text.lower():
            return datetime.utcnow().replace(day=1) + timedelta(days=32)
        elif 'next quarter' in commitment_text.lower():
            current_month = datetime.utcnow().month
            quarter_start = ((current_month - 1) // 3 + 1) * 3 + 1
            if quarter_start > 12:
                quarter_start = 1
                year = datetime.utcnow().year + 1
            else:
                year = datetime.utcnow().year
            return datetime(year, quarter_start, 1)
        elif 'next year' in commitment_text.lower():
            return datetime(datetime.utcnow().year + 1, 1, 1)
        
        return None
    
    def _assess_commitment_risk(self, commitment_text: str, context: str) -> str:
        """Assess risk level of commitment"""
        high_risk_keywords = ['complex', 'difficult', 'challenging', 'resource-intensive']
        medium_risk_keywords = ['require', 'need', 'coordinate', 'multiple']
        
        text_lower = (commitment_text + ' ' + context).lower()
        
        if any(keyword in text_lower for keyword in high_risk_keywords):
            return 'high'
        elif any(keyword in text_lower for keyword in medium_risk_keywords):
            return 'medium'
        else:
            return 'low'
    
    def _suggest_verification_method(self, category: str) -> str:
        """Suggest verification method based on commitment category"""
        verification_methods = {
            'rectification': 'automated_testing',
            'implementation': 'manual_review',
            'policy_change': 'document_review',
            'system_enhancement': 'user_acceptance_testing',
            'investigation': 'peer_review',
            'procurement': 'vendor_confirmation',
            'general': 'manual_verification'
        }
        
        return verification_methods.get(category, 'manual_verification')
    
    def _classify_query_category(self, query_text: str, similar_queries: List[Dict]) -> QueryCategory:
        """Classify query category"""
        # Category keywords
        category_keywords = {
            QueryCategory.FINANCIAL: ['budget', 'finance', 'cost', 'expense', 'revenue', 'audit', 'accounting'],
            QueryCategory.COMPLIANCE: ['compliance', 'regulation', 'requirement', 'standard', 'policy', 'procedure'],
            QueryCategory.OPERATIONAL: ['operation', 'process', 'workflow', 'procedure', 'daily', 'routine'],
            QueryCategory.TECHNICAL: ['system', 'software', 'hardware', 'technology', 'database', 'network'],
            QueryCategory.POLICY: ['policy', 'rule', 'guideline', 'directive', 'regulation'],
            QueryCategory.HUMAN_RESOURCES: ['employee', 'staff', 'personnel', 'hr', 'training', 'recruitment'],
            QueryCategory.LEGAL: ['legal', 'law', 'contract', 'agreement', 'litigation', 'court'],
            QueryCategory.PROCUREMENT: ['procurement', 'purchase', 'vendor', 'supplier', 'contract', 'bid']
        }
        
        query_lower = query_text.lower()
        
        # Count keyword matches for each category
        category_scores = {}
        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            category_scores[category] = score
        
        # Add weight from similar queries
        for similar in similar_queries:
            if similar.get('category'):
                similar_category = QueryCategory(similar['category'])
                if similar_category in category_scores:
                    category_scores[similar_category] += similar.get('similarity_score', 0) * 2
        
        # Return category with highest score
        if category_scores:
            best_category = max(category_scores, key=category_scores.get)
            if category_scores[best_category] > 0:
                return best_category
        
        return QueryCategory.OPERATIONAL  # Default category
    
    def _assess_query_complexity(self, query_text: str, similar_queries: List[Dict]) -> QueryComplexity:
        """Assess query complexity"""
        complexity_indicators = {
            QueryComplexity.SIMPLE: ['what', 'who', 'when', 'where'],
            QueryComplexity.MODERATE: ['how', 'why', 'which'],
            QueryComplexity.COMPLEX: ['analyze', 'evaluate', 'compare', 'relationship', 'impact'],
            QueryComplexity.CRITICAL: ['urgent', 'critical', 'emergency', 'immediate', 'asap']
        }
        
        query_lower = query_text.lower()
        
        # Count indicators
        complexity_scores = {}
        for complexity, indicators in complexity_indicators.items():
            score = sum(1 for indicator in indicators if indicator in query_lower)
            complexity_scores[complexity] = score
        
        # Consider query length
        if len(query_text) > 500:
            complexity_scores[QueryComplexity.COMPLEX] += 1
        elif len(query_text) > 200:
            complexity_scores[QueryComplexity.MODERATE] += 1
        
        # Consider similar queries complexity
        for similar in similar_queries:
            if similar.get('complexity'):
                similar_complexity = QueryComplexity(similar['complexity'])
                if similar_complexity in complexity_scores:
                    complexity_scores[similar_complexity] += 1
        
        # Return complexity with highest score
        if complexity_scores:
            best_complexity = max(complexity_scores, key=complexity_scores.get)
            if complexity_scores[best_complexity] > 0:
                return best_complexity
        
        return QueryComplexity.MODERATE  # Default complexity
    
    def _assess_urgency_level(self, query_text: str, detected_commitments: List[CommitmentAnalysis]) -> UrgencyLevel:
        """Assess urgency level"""
        urgency_keywords = {
            UrgencyLevel.CRITICAL: ['urgent', 'critical', 'emergency', 'immediate', 'asap', 'deadline'],
            UrgencyLevel.HIGH: ['important', 'priority', 'soon', 'quickly', 'promptly'],
            UrgencyLevel.MEDIUM: ['need', 'require', 'request', 'please'],
            UrgencyLevel.LOW: ['information', 'clarification', 'general', 'routine']
        }
        
        query_lower = query_text.lower()
        
        # Count urgency indicators
        urgency_scores = {}
        for urgency, keywords in urgency_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            urgency_scores[urgency] = score
        
        # Consider detected commitments
        for commitment in detected_commitments:
            if commitment.priority == 'high':
                urgency_scores[UrgencyLevel.HIGH] += 2
            elif commitment.priority == 'medium':
                urgency_scores[UrgencyLevel.MEDIUM] += 1
        
        # Consider commitment deadlines
        for commitment in detected_commitments:
            if commitment.estimated_completion:
                days_until = (commitment.estimated_completion - datetime.utcnow()).days
                if days_until < 7:
                    urgency_scores[UrgencyLevel.HIGH] += 3
                elif days_until < 30:
                    urgency_scores[UrgencyLevel.MEDIUM] += 2
        
        # Return urgency with highest score
        if urgency_scores:
            best_urgency = max(urgency_scores, key=urgency_scores.get)
            if urgency_scores[best_urgency] > 0:
                return best_urgency
        
        return UrgencyLevel.MEDIUM  # Default urgency
    
    def _calculate_confidence_score(self, similar_queries: List[Dict], 
                                  suggested_responses: List[Dict], 
                                  detected_commitments: List[CommitmentAnalysis]) -> float:
        """Calculate overall confidence score for the analysis"""
        confidence = 0.5  # Base confidence
        
        # Add confidence from similar queries
        if similar_queries:
            avg_similarity = sum(q.get('similarity_score', 0) for q in similar_queries) / len(similar_queries)
            confidence += avg_similarity * 0.3
        
        # Add confidence from suggested responses
        if suggested_responses:
            avg_response_confidence = sum(r.get('confidence', 0) for r in suggested_responses) / len(suggested_responses)
            confidence += avg_response_confidence * 0.2
        
        # Add confidence from detected commitments
        if detected_commitments:
            avg_commitment_confidence = sum(c.confidence for c in detected_commitments) / len(detected_commitments)
            confidence += avg_commitment_confidence * 0.1
        
        return min(confidence, 1.0)  # Cap at 1.0
    
    def create_query(self, query_data: Dict) -> AuditQuery:
        """
        Create a new audit query without AI analysis

        Args:
            query_data: Dictionary containing query information

        Returns:
            AuditQuery object
        """
        # Extract query text
        query_text = query_data.get('query_description', '')
        state_name = query_data.get('state_name')

        # Create audit query
        audit_query = AuditQuery(
            query_id=query_data.get('query_id', self._generate_query_id()),
            state_name=state_name,
            date_received=query_data.get('date_received', datetime.utcnow().date()),
            query_description=query_text,
            assigned_official=query_data.get('assigned_official'),
            assigned_official_email=query_data.get('assigned_official_email'),
            department=query_data.get('department'),
            priority=query_data.get('priority', 'medium'),
            status=AuditQueryStatus(query_data.get('status', 'received')),
            memo_id=query_data.get('memo_id'),
            audit_year=query_data.get('audit_year'),
            audit_type=query_data.get('audit_type'),
            source_document=query_data.get('source_document')
        )

        # Generate and store embedding
        embedding = get_bert_embeddings([query_text])[0]
        audit_query.embedding = embedding.tobytes()

        # Save to database
        db.session.add(audit_query)
        db.session.flush()  # Get the ID without committing

        # Create version history
        version = QueryVersion(
            audit_query_id=audit_query.id,
            version_number=1,
            change_type='created',
            new_status=audit_query.status,
            changed_by=query_data.get('created_by', 'system'),
            change_reason='Initial query creation',
            full_snapshot={
                'query_data': query_data
            }
        )
        db.session.add(version)

        # Log the activity
        log_entry = Logs(
            action=f"Created query {audit_query.query_id}",
            user_email=query_data.get('created_by', 'system'),
            timestamp=datetime.utcnow()
        )
        db.session.add(log_entry)

        # Commit all changes
        db.session.commit()

        return audit_query

    def create_query_with_analysis(self, query_data: Dict) -> Tuple[AuditQuery, QueryAnalysis]:
        """
        Create a new audit query with AI analysis

        Args:
            query_data: Dictionary containing query information

        Returns:
            Tuple of (AuditQuery, QueryAnalysis)
        """
        # Extract query text for analysis
        query_text = query_data.get('query_description', '')
        state_name = query_data.get('state_name')

        # Perform AI analysis
        analysis = self.analyze_query(query_text, state_name)

        # Create audit query
        audit_query = AuditQuery(
            query_id=query_data.get('query_id', self._generate_query_id()),
            state_name=state_name,
            date_received=query_data.get('date_received', datetime.utcnow().date()),
            query_description=query_text,
            assigned_official=query_data.get('assigned_official'),
            assigned_official_email=query_data.get('assigned_official_email'),
            department=query_data.get('department'),
            priority=query_data.get('priority', 'medium'),
            status=AuditQueryStatus(query_data.get('status', 'received')),
            memo_id=query_data.get('memo_id'),
            audit_year=query_data.get('audit_year'),
            audit_type=query_data.get('audit_type'),
            source_document=query_data.get('source_document')
        )

        # Generate and store embedding
        embedding = get_bert_embeddings([query_text])[0]
        audit_query.embedding = embedding.tobytes()

        # Save to database
        db.session.add(audit_query)
        db.session.flush()  # Get the ID without committing

        # Update analysis with query ID
        analysis.query_id = audit_query.id

        # Create commitments if detected
        if analysis.detected_commitments:
            for commitment_analysis in analysis.detected_commitments:
                commitment = Commitment(
                    audit_query_id=audit_query.id,
                    commitment_text=commitment_analysis.commitment_text,
                    commitment_type=commitment_analysis.category,
                    target_date=commitment_analysis.estimated_completion,
                    status=CommitmentStatus.pending,
                    detected_at=datetime.utcnow(),
                    responsible_party=commitment_analysis.responsible_party,
                    verification_method=commitment_analysis.verification_method
                )
                db.session.add(commitment)

        # Create version history
        version = QueryVersion(
            audit_query_id=audit_query.id,
            version_number=1,
            change_type='created',
            new_status=audit_query.status,
            changed_by=query_data.get('created_by', 'system'),
            change_reason='Initial query creation with AI analysis',
            full_snapshot={
                'query_data': query_data,
                'analysis': {
                    'category': analysis.category.value,
                    'complexity': analysis.complexity.value,
                    'urgency': analysis.urgency.value,
                    'confidence_score': analysis.confidence_score,
                    'similar_queries_count': len(analysis.similar_queries),
                    'suggested_responses_count': len(analysis.suggested_responses),
                    'detected_commitments_count': len(analysis.detected_commitments)
                }
            }
        )
        db.session.add(version)

        # Log the activity
        log_entry = Logs(
            action=f"Created query {audit_query.query_id} with AI analysis",
            user_email=query_data.get('created_by', 'system'),
            timestamp=datetime.utcnow()
        )
        db.session.add(log_entry)

        # Commit all changes
        db.session.commit()

        return audit_query, analysis
    
    def _generate_query_id(self) -> str:
        """Generate unique query ID"""
        year = datetime.utcnow().year
        # Get count of queries this year
        count = AuditQuery.query.filter(
            func.extract('year', AuditQuery.date_received) == year
        ).count()
        
        return f"AUD-{year}-{count + 1:04d}"
    
    def get_query_insights(self, query_id: int) -> Dict:
        """
        Get comprehensive insights for a specific query
        
        Args:
            query_id: ID of the query to analyze
            
        Returns:
            Dictionary with comprehensive insights
        """
        query = AuditQuery.query.get(query_id)
        if not query:
            return {}
        
        # Get similar queries
        if query.embedding:
            embedding = np.frombuffer(query.embedding, dtype=np.float32)
            similar_queries = self._find_similar_queries(
                query.query_description, 
                embedding, 
                query.state_name
            )
        else:
            similar_queries = []
        
        # Get commitment status
        commitments = Commitment.query.filter_by(audit_query_id=query_id).all()
        
        # Get version history
        versions = QueryVersion.query.filter_by(audit_query_id=query_id).order_by(
            desc(QueryVersion.version_number)
        ).all()
        
        # Calculate metrics
        insights = {
            'query_info': {
                'id': query.id,
                'query_id': query.query_id,
                'description': query.query_description,
                'state_name': query.state_name,
                'status': query.status.value,
                'priority': query.priority,
                'date_received': query.date_received.isoformat(),
                'assigned_official': query.assigned_official,
                'department': query.department
            },
            'similar_queries': similar_queries[:5],
            'commitments': [
                {
                    'id': c.id,
                    'text': c.commitment_text,
                    'status': c.status.value,
                    'target_date': c.target_date.isoformat() if c.target_date else None,
                    'days_until_target': (c.target_date - datetime.utcnow().date()).days if c.target_date else None,
                    'risk_level': self._assess_commitment_risk(c.commitment_text, '')
                }
                for c in commitments
            ],
            'version_history': [
                {
                    'version': v.version_number,
                    'change_type': v.change_type,
                    'changed_by': v.changed_by,
                    'change_reason': v.change_reason,
                    'timestamp': v.change_timestamp.isoformat()
                }
                for v in versions
            ],
            'metrics': {
                'total_similar_queries': len(similar_queries),
                'active_commitments': len([c for c in commitments if c.status in [CommitmentStatus.pending, CommitmentStatus.in_progress]]),
                'overdue_commitments': len([c for c in commitments if c.status == CommitmentStatus.overdue]),
                'version_count': len(versions),
                'days_open': (datetime.utcnow().date() - query.date_received).days
            }
        }
        
        return insights
    
    def get_performance_metrics(self, date_range: Dict = None) -> Dict:
        """
        Get performance metrics for the query tracking system
        
        Args:
            date_range: Optional date range filter
            
        Returns:
            Dictionary with performance metrics
        """
        if not date_range:
            date_range = {
                'start': datetime.utcnow() - timedelta(days=30),
                'end': datetime.utcnow()
            }
        
        start_date = date_range['start']
        end_date = date_range['end']
        
        # Query volume metrics
        total_queries = AuditQuery.query.filter(
            AuditQuery.date_received >= start_date,
            AuditQuery.date_received <= end_date
        ).count()
        
        queries_by_status = db.session.query(
            AuditQuery.status, func.count(AuditQuery.id)
        ).filter(
            AuditQuery.date_received >= start_date,
            AuditQuery.date_received <= end_date
        ).group_by(AuditQuery.status).all()
        
        # Response time metrics
        responded_queries = AuditQuery.query.filter(
            AuditQuery.date_received >= start_date,
            AuditQuery.date_received <= end_date,
            AuditQuery.response_date.isnot(None)
        ).all()
        
        response_times = []
        for query in responded_queries:
            if query.response_date:
                response_days = (query.response_date - query.date_received).days
                response_times.append(response_days)
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Commitment metrics
        commitments = Commitment.query.filter(
            Commitment.detected_at >= start_date,
            Commitment.detected_at <= end_date
        ).all()
        
        commitment_status_counts = {}
        for status in CommitmentStatus:
            count = len([c for c in commitments if c.status == status])
            commitment_status_counts[status.value] = count
        
        completion_rate = commitment_status_counts.get('completed', 0) / len(commitments) if commitments else 0
        
        # Department metrics
        department_metrics = db.session.query(
            AuditQuery.department, func.count(AuditQuery.id)
        ).filter(
            AuditQuery.date_received >= start_date,
            AuditQuery.date_received <= end_date
        ).group_by(AuditQuery.department).all()
        
        return {
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': (end_date - start_date).days
            },
            'query_volume': {
                'total_queries': total_queries,
                'daily_average': total_queries / (end_date - start_date).days,
                'by_status': {status.value: count for status, count in queries_by_status}
            },
            'response_times': {
                'average_days': avg_response_time,
                'median_days': sorted(response_times)[len(response_times)//2] if response_times else 0,
                'total_responded': len(responded_queries),
                'response_rate': len(responded_queries) / total_queries if total_queries > 0 else 0
            },
            'commitments': {
                'total_commitments': len(commitments),
                'completion_rate': completion_rate,
                'by_status': commitment_status_counts
            },
            'departments': {dept: count for dept, count in department_metrics},
            'ai_performance': {
                'cache_hit_rate': len(self.cache) / max(len(self.cache) + 100, 1),  # Estimated
                'avg_analysis_time_ms': 1500,  # Estimated based on typical performance
                'similarity_matches_found': len([q for q in AuditQuery.query.all() if q.embedding])
            }
        }
