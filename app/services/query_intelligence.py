import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import numpy as np
from flask import current_app

from app import db
from app.models import FAQ, DraftFAQ
from app.audit_models import AuditQuery, Commitment, CommitmentStatus
from app.utils.embeddings import get_bert_embeddings, normalize, find_related_questions_scored


class QueryIntelligenceService:
    """Local AI-powered query intelligence and response suggestion system"""
    
    def __init__(self):
        self.response_categories = {
            'policy': ['policy', 'guideline', 'procedure', 'protocol', 'rule'],
            'technical': ['system', 'technical', 'implementation', 'development', 'code'],
            'financial': ['budget', 'cost', 'financial', 'expenditure', 'fund'],
            'compliance': ['compliance', 'audit', 'regulation', 'requirement', 'standard'],
            'operational': ['operation', 'process', 'workflow', 'procedure', 'manual']
        }
        
        self.urgency_indicators = {
            'high': ['urgent', 'immediately', 'asap', 'emergency', 'critical'],
            'medium': ['soon', 'promptly', 'quickly', 'expedite'],
            'low': ['when convenient', 'at your earliest', 'no rush']
        }
    
    def analyze_query_intent(self, query_text: str) -> Dict:
        """Analyze query intent and extract key information"""
        analysis = {
            'category': self.categorize_query(query_text),
            'urgency': self.detect_urgency(query_text),
            'entities': self.extract_entities(query_text),
            'sentiment': self.analyze_sentiment(query_text),
            'complexity': self.assess_complexity(query_text),
            'keywords': self.extract_keywords(query_text)
        }
        
        return analysis
    
    def categorize_query(self, query_text: str) -> str:
        """Categorize query into predefined categories"""
        text_lower = query_text.lower()
        scores = {}
        
        for category, keywords in self.response_categories.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            scores[category] = score
        
        return max(scores, key=scores.get) if any(scores.values()) else 'general'
    
    def detect_urgency(self, query_text: str) -> str:
        """Detect urgency level from query text"""
        text_lower = query_text.lower()
        
        for urgency, indicators in self.urgency_indicators.items():
            if any(indicator in text_lower for indicator in indicators):
                return urgency
        
        return 'medium'
    
    def extract_entities(self, query_text: str) -> Dict[str, List[str]]:
        """Extract named entities from query text"""
        entities = {
            'states': [],
            'departments': [],
            'dates': [],
            'numbers': [],
            'references': []
        }
        
        # Extract states (common Indian states)
        states_pattern = r'\b(?:Andhra Pradesh|Arunachal Pradesh|Assam|Bihar|Chhattisgarh|Goa|Gujarat|Haryana|Himachal Pradesh|Jharkhand|Karnataka|Kerala|Madhya Pradesh|Maharashtra|Manipur|Meghalaya|Mizoram|Nagaland|Odisha|Punjab|Rajasthan|Sikkim|Tamil Nadu|Telangana|Tripura|Uttar Pradesh|Uttarakhand|West Bengal|Delhi|Mumbai|Kolkata|Chennai|Bangalore|Hyderabad)\b'
        entities['states'] = re.findall(states_pattern, query_text, re.IGNORECASE)
        
        # Extract departments
        dept_pattern = r'\b(?:department|ministry|directorate|office|bureau|commission|board|corporation|authority)\s+(?:of|for)?\s*([a-zA-Z\s]+?)(?:\s|$|,|\.|;)'
        entities['departments'] = [match.strip() for match in re.findall(dept_pattern, query_text, re.IGNORECASE)]
        
        # Extract dates
        date_pattern = r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{2,4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b'
        entities['dates'] = re.findall(date_pattern, query_text)
        
        # Extract numbers and references
        ref_pattern = r'\b(?:ref|reference|memo|letter|file|case|query|audit)\s*#?\s*([A-Z0-9-/]+)\b'
        entities['references'] = [match.strip() for match in re.findall(ref_pattern, query_text, re.IGNORECASE)]
        
        number_pattern = r'\b\d+(?:,\d{3})*(?:\.\d+)?\b'
        entities['numbers'] = re.findall(number_pattern, query_text)
        
        return entities
    
    def analyze_sentiment(self, query_text: str) -> str:
        """Simple sentiment analysis"""
        positive_words = ['thank', 'appreciate', 'good', 'excellent', 'satisfied', 'pleased']
        negative_words = ['problem', 'issue', 'concern', 'dissatisfied', 'complaint', 'urgent', 'delay']
        
        text_lower = query_text.lower()
        pos_score = sum(1 for word in positive_words if word in text_lower)
        neg_score = sum(1 for word in negative_words if word in text_lower)
        
        if pos_score > neg_score:
            return 'positive'
        elif neg_score > pos_score:
            return 'negative'
        else:
            return 'neutral'
    
    def assess_complexity(self, query_text: str) -> str:
        """Assess query complexity based on length and structure"""
        word_count = len(query_text.split())
        
        # Check for complex indicators
        complex_indicators = ['multiple', 'various', 'several', 'complex', 'detailed', 'comprehensive']
        has_complex_indicators = any(indicator in query_text.lower() for indicator in complex_indicators)
        
        # Check for multiple questions
        question_count = len(re.findall(r'\?', query_text))
        
        if word_count > 100 or has_complex_indicators or question_count > 1:
            return 'high'
        elif word_count > 50 or question_count == 1:
            return 'medium'
        else:
            return 'low'
    
    def extract_keywords(self, query_text: str) -> List[str]:
        """Extract important keywords from query"""
        # Simple keyword extraction - remove stop words and get important terms
        stop_words = {'the', 'is', 'at', 'which', 'on', 'and', 'a', 'an', 'as', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall', 'must', 'to', 'of', 'in', 'for', 'with', 'by', 'from', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once'}
        
        words = re.findall(r'\b[a-zA-Z]{3,}\b', query_text.lower())
        keywords = [word for word in words if word not in stop_words and len(word) > 3]
        
        # Return top keywords by frequency
        from collections import Counter
        word_freq = Counter(keywords)
        return [word for word, count in word_freq.most_common(10)]
    
    def find_similar_queries(self, query_text: str, state_name: str = None, limit: int = 10) -> List[Dict]:
        """Find similar historical queries using vector search"""
        # Search in FAQ database
        similar_faqs = find_related_questions_scored(query_text, "", "", state_name)
        
        # Search in audit queries if available
        similar_audit_queries = []
        try:
            emb = normalize(get_bert_embeddings(query_text))
            if emb is not None:
                audit_queries = AuditQuery.query.filter(
                    AuditQuery.embedding.cosine_distance(emb) <= 0.3
                ).order_by(AuditQuery.embedding.cosine_distance(emb)).limit(limit).all()
                
                for aq in audit_queries:
                    similar_audit_queries.append({
                        'query_id': aq.query_id,
                        'description': aq.query_description,
                        'response': aq.response_provided,
                        'state': aq.state_name,
                        'date': aq.date_received.isoformat() if aq.date_received else None,
                        'status': aq.status.value if aq.status else None
                    })
        except Exception as e:
            current_app.logger.warning(f"Audit query search failed: {str(e)}")
        
        # Combine and rank results
        all_similar = []
        
        # Add FAQ results
        for faq in similar_faqs:
            all_similar.append({
                'type': 'faq',
                'question': faq['question'],
                'answer': faq['reply'],
                'state': faq['state_name'],
                'similarity': faq['similarity'],
                'memo_id': faq['memo_id']
            })
        
        # Add audit query results
        for aq in similar_audit_queries:
            all_similar.append({
                'type': 'audit_query',
                'question': aq['description'],
                'answer': aq['response'],
                'state': aq['state'],
                'similarity': 0.8,  # Default similarity for audit queries
                'query_id': aq['query_id'],
                'date': aq['date'],
                'status': aq['status']
            })
        
        # Sort by similarity
        all_similar.sort(key=lambda x: x['similarity'], reverse=True)
        
        return all_similar[:limit]
    
    def suggest_responses(self, query_text: str, analysis: Dict = None) -> List[Dict]:
        """Suggest possible responses based on similar queries and analysis"""
        if analysis is None:
            analysis = self.analyze_query_intent(query_text)
        
        suggestions = []
        
        # Get similar queries
        similar = self.find_similar_queries(query_text, limit=5)
        
        # Generate suggestions based on similar queries
        for item in similar:
            if item.get('answer') and item['similarity'] > 0.7:
                suggestion = {
                    'type': 'historical',
                    'response': item['answer'],
                    'confidence': item['similarity'],
                    'source': f"Similar {item['type'].replace('_', ' ').title()}",
                    'source_details': f"State: {item.get('state', 'Unknown')}",
                    'category': analysis['category']
                }
                suggestions.append(suggestion)
        
        # Generate template-based suggestions
        template_suggestions = self.generate_template_responses(analysis)
        suggestions.extend(template_suggestions)
        
        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return suggestions[:5]  # Return top 5 suggestions
    
    def generate_template_responses(self, analysis: Dict) -> List[Dict]:
        """Generate template responses based on query analysis"""
        templates = []
        
        category = analysis['category']
        urgency = analysis['urgency']
        sentiment = analysis['sentiment']
        
        # Category-specific templates
        if category == 'policy':
            templates.append({
                'type': 'template',
                'response': "As per the current policy guidelines, the matter is being reviewed. We will provide a detailed response in accordance with established procedures.",
                'confidence': 0.6,
                'source': 'Policy Template',
                'category': category
            })
        
        elif category == 'technical':
            templates.append({
                'type': 'template',
                'response': "The technical team has been notified and is investigating the issue. We will provide an update on the resolution timeline shortly.",
                'confidence': 0.6,
                'source': 'Technical Template',
                'category': category
            })
        
        elif category == 'financial':
            templates.append({
                'type': 'template',
                'response': "The financial matter is under review by the accounts department. We will ensure proper verification before providing a response.",
                'confidence': 0.6,
                'source': 'Financial Template',
                'category': category
            })
        
        # Urgency-specific adjustments
        if urgency == 'high':
            templates.append({
                'type': 'template',
                'response': "This matter has been marked as high priority and is being handled on an urgent basis. You can expect a response within 24-48 hours.",
                'confidence': 0.7,
                'source': 'Urgent Response Template',
                'category': category
            })
        
        # Sentiment-specific adjustments
        if sentiment == 'negative':
            templates.append({
                'type': 'template',
                'response': "We understand your concern and apologize for any inconvenience caused. This matter has our immediate attention and we are working to resolve it promptly.",
                'confidence': 0.6,
                'source': 'Concern Response Template',
                'category': category
            })
        
        return templates
    
    def detect_commitments(self, response_text: str) -> List[Dict]:
        """Detect and extract commitments from response text"""
        commitments = []
        
        commitment_patterns = [
            (r"will be (?:rectified|fixed|resolved|implemented|addressed) (?:by|before|on) (\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", 'rectification'),
            (r"will be implemented (?:by|before|on) (\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", 'implementation'),
            (r"will be (?:rectified|fixed|resolved|implemented|addressed) (?:in|within) (\d+)\s+(?:days|weeks|months)", 'rectification'),
            (r"next (?:release|version|update) (?:is scheduled|will be available) (?:by|before|on) (\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", 'release'),
        ]
        
        for pattern, commitment_type in commitment_patterns:
            matches = re.finditer(pattern, response_text, re.IGNORECASE)
            
            for match in matches:
                commitment_text = match.group(0)
                target_date_str = match.group(1) if match.groups() else None
                
                # Parse target date
                target_date = None
                if target_date_str:
                    try:
                        if re.match(r'\d+', target_date_str):
                            # Relative time (e.g., "15 days")
                            if 'days' in commitment_text.lower():
                                days = int(target_date_str)
                                target_date = datetime.now() + timedelta(days=days)
                            elif 'weeks' in commitment_text.lower():
                                weeks = int(target_date_str)
                                target_date = datetime.now() + timedelta(weeks=weeks)
                            elif 'months' in commitment_text.lower():
                                months = int(target_date_str)
                                target_date = datetime.now() + timedelta(days=months * 30)
                        else:
                            # Absolute date
                            target_date = datetime.strptime(target_date_str, '%d-%m-%Y')
                    except (ValueError, TypeError):
                        target_date = None
                
                commitments.append({
                    'text': commitment_text,
                    'type': commitment_type,
                    'target_date': target_date.isoformat() if target_date else None,
                    'confidence': 0.8
                })
        
        return commitments
    
    def get_query_statistics(self, state_name: str = None, days: int = 30) -> Dict:
        """Get query statistics for dashboard"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Base query
        query = AuditQuery.query.filter(
            AuditQuery.created_at >= start_date,
            AuditQuery.created_at <= end_date
        )
        
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        # Get statistics
        total_queries = query.count()
        
        status_breakdown = {}
        for status in AuditQueryStatus:
            status_count = query.filter(AuditQuery.status == status).count()
            status_breakdown[status.value] = status_count
        
        # Commitment statistics
        commitment_query = Commitment.query.filter(
            Commitment.created_at >= start_date,
            Commitment.created_at <= end_date
        )
        
        if state_name:
            commitment_query = commitment_query.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        total_commitments = commitment_query.count()
        overdue_commitments = commitment_query.filter(
            Commitment.target_date < datetime.now().date(),
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        ).count()
        
        return {
            'period_days': days,
            'state': state_name or 'All States',
            'total_queries': total_queries,
            'status_breakdown': status_breakdown,
            'total_commitments': total_commitments,
            'overdue_commitments': overdue_commitments,
            'completion_rate': self.calculate_completion_rate(commitment_query)
        }
    
    def calculate_completion_rate(self, commitment_query) -> float:
        """Calculate commitment completion rate"""
        total = commitment_query.count()
        if total == 0:
            return 0.0
        
        completed = commitment_query.filter(Commitment.status == CommitmentStatus.completed).count()
        return (completed / total) * 100
    
    def generate_insights(self, state_name: str = None) -> List[Dict]:
        """Generate insights from query data"""
        insights = []
        
        # Get recent trends
        recent_queries = AuditQuery.query.filter(
            AuditQuery.created_at >= datetime.now() - timedelta(days=30)
        )
        
        if state_name:
            recent_queries = recent_queries.filter(AuditQuery.state_name == state_name)
        
        # Analyze common categories
        categories = {}
        for query in recent_queries:
            analysis = self.analyze_query_intent(query.query_description)
            category = analysis['category']
            categories[category] = categories.get(category, 0) + 1
        
        if categories:
            top_category = max(categories, key=categories.get)
            insights.append({
                'type': 'trend',
                'title': f'Most Common Query Category',
                'description': f"{top_category.title()} queries are most frequent ({categories[top_category]} queries)",
                'priority': 'medium'
            })
        
        # Check for overdue commitments
        overdue_count = Commitment.query.filter(
            Commitment.target_date < datetime.now().date(),
            Commitment.status.in_([CommitmentStatus.pending, CommitmentStatus.in_progress])
        )
        
        if state_name:
            overdue_count = overdue_count.join(AuditQuery).filter(AuditQuery.state_name == state_name)
        
        overdue_count = overdue_count.count()
        
        if overdue_count > 0:
            insights.append({
                'type': 'alert',
                'title': 'Overdue Commitments',
                'description': f"{overdue_count} commitments are overdue and require attention",
                'priority': 'high'
            })
        
        # Response time analysis
        avg_response_time = self.calculate_average_response_time(state_name)
        if avg_response_time:
            insights.append({
                'type': 'performance',
                'title': 'Average Response Time',
                'description': f"Current average response time: {avg_response_time:.1f} days",
                'priority': 'low' if avg_response_time < 7 else 'medium'
            })
        
        return insights
    
    def calculate_average_response_time(self, state_name: str = None) -> Optional[float]:
        """Calculate average response time in days"""
        query = AuditQuery.query.filter(
            AuditQuery.response_date.isnot(None),
            AuditQuery.date_received.isnot(None)
        )
        
        if state_name:
            query = query.filter(AuditQuery.state_name == state_name)
        
        queries = query.all()
        if not queries:
            return None
        
        total_days = 0
        count = 0
        
        for q in queries:
            if q.response_date and q.date_received:
                days = (q.response_date - q.date_received).days
                if days >= 0:  # Filter out invalid dates
                    total_days += days
                    count += 1
        
        return total_days / count if count > 0 else None
