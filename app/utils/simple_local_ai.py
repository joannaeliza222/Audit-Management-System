"""
Simple Local AI Assistant Implementation
Privacy-preserving AI that works completely offline
"""

import os
import re
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

class SimpleLocalAI:
    """
    Privacy-preserving AI assistant that works completely offline
    No external API calls, no data transmission
    """
    
    def __init__(self):
        self.responses_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'ai_responses.json')
        self.patterns_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'response_patterns.json')
        self.load_patterns()
    
    def load_patterns(self):
        """Load response patterns from local file"""
        try:
            patterns_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'response_patterns.json')
            
            if os.path.exists(patterns_file):
                with open(patterns_file, 'r') as f:
                    self.patterns = json.load(f)
            else:
                self.patterns = {
                    'greeting': ['Hello! How can I help you today?', 'Welcome! What can I assist you with?'],
                    'technical': ['I understand you\'re experiencing a technical issue. Let me help you with that.', 
                               'This appears to be a technical matter. Let me guide you through the solution.'],
                    'process': ['I can help you with this process-related question.', 
                              'Let me explain the procedure for this process.'],
                    'policy': ['I can provide information about our policies and guidelines.', 
                              'Let me check the relevant policy for you.'],
                    'data': ['I can assist you with data-related queries and reports.', 
                            'Let me help you with your data request.'],
                    'version': ['This issue has been addressed in a specific version. Let me check that for you.',
                              'I have information about this version-specific issue.'],
                    'fallback': ['I apologize, but I don\'t have specific information about that.', 
                              'Let me connect you with someone who can better assist you.']
                }
        except Exception as e:
            self.patterns = {
                'greeting': ['Hello! How can I help you today?'],
                'technical': ['I understand you\'re experiencing a technical issue.'],
                'process': ['I can help you with this process-related question.'],
                'policy': ['I can provide information about our policies and guidelines.'],
                'data': ['I can assist you with data-related queries and reports.'],
                'version': ['This issue has been addressed in a specific version.'],
                'fallback': ['I apologize, but I don\'t have specific information about that.']
            }
    
    def generate_response(self, question: str, context: Optional[Dict] = None) -> Dict:
        """
        Generate response using local patterns and context
        Completely offline, no data leakage
        """
        try:
            question_lower = question.lower().strip()
            
            # Check for export requests
            export_response = self.handle_export_request(question, context)
            if export_response:
                return export_response
            
            # Check for FAQ answers first (highest priority)
            faq_response = self.check_version_context(question, context)
            if faq_response and faq_response.get('response_type') == 'faq_resolution':
                return faq_response
            
            # Check for version-specific responses second
            version_response = self.check_version_context(question, context)
            if version_response:
                return version_response
            
            # Pattern-based response generation
            response_type = self.classify_question_type(question_lower)
            
            if response_type in self.patterns:
                responses = self.patterns[response_type]
                base_response = responses[hash(question) % len(responses)]
                
                # Add context if available
                if context:
                    base_response = self.add_context_to_response(base_response, context)
                
                return {
                    'response': base_response,
                    'confidence': 0.8,
                    'source': 'local_pattern',
                    'response_type': response_type,
                    'context_used': context is not None
                }
            
            # Fallback response
            fallback_response = self.patterns['fallback'][0]
            
            return {
                'response': fallback_response,
                'confidence': 0.3,
                'source': 'local_fallback',
                'response_type': 'fallback',
                'context_used': False
            }
            
        except Exception as e:
            return {
                'response': 'I apologize, but I encountered an error while processing your request.',
                'confidence': 0.1,
                'source': 'error',
                'error': str(e)
            }
    
    def handle_export_request(self, question: str, context: Optional[Dict]) -> Optional[Dict]:
        """Handle data export requests through chat"""
        question_lower = question.lower()
        
        # Check if this is an export request
        export_keywords = ['export', 'download', 'data export', 'export data', 'get data']
        if not any(keyword in question_lower for keyword in export_keywords):
            return None
        
        # Check for specific data types
        if 'faq' in question_lower or 'question' in question_lower:
            return {
                'response': '''I can help you export FAQ data! Let me prepare that for you.

**Export Options:**
• FAQ Database - All answered questions
• Filter by state (optional)

Please specify:
1. Which state's data would you like? (or "all states")
2. Any specific filters needed?

Once you confirm, I'll generate the Excel file for download.''',
                'confidence': 0.9,
                'source': 'export_assistant',
                'response_type': 'export_request',
                'export_type': 'faq'
            }
        
        elif 'future issue' in question_lower or 'version' in question_lower:
            return {
                'response': '''I can help you export Future Issues data! Let me prepare that for you.

**Export Options:**
• Future Issues - Version-specific problems
• Filter by status (optional)

Please specify:
1. Which status? ("addressed", "not addressed", or "all")
2. Any specific source portal?

Once you confirm, I'll generate the Excel file for download.''',
                'confidence': 0.9,
                'source': 'export_assistant',
                'response_type': 'export_request',
                'export_type': 'future_issues'
            }
        
        else:
            return {
                'response': '''I can help you export data! Here are the available options:

**Available Exports:**
• FAQ Database - All answered questions
• Future Issues - Version-specific problems

Please let me know:
1. Which data type you want (FAQ or Future Issues)
2. Any specific filters needed

I'll generate the Excel file for you immediately!''',
                'confidence': 0.9,
                'source': 'export_assistant',
                'response_type': 'export_request',
                'export_type': 'general'
            }
    
    def classify_question_type(self, question: str) -> str:
        """Classify question type using simple keyword matching"""
        
        # Version issues
        version_keywords = ['version', 'v1', 'v2', 'v3', 'fixed', 'rectified', 'resolved']
        if any(keyword in question for keyword in version_keywords):
            return 'version'
        
        # Technical issues
        technical_keywords = ['error', 'bug', 'issue', 'problem', 'not working', 'broken', 'failed', 'crash']
        if any(keyword in question for keyword in technical_keywords):
            return 'technical'
        
        # Process questions
        process_keywords = ['how to', 'procedure', 'process', 'workflow', 'steps', 'guide']
        if any(keyword in question for keyword in process_keywords):
            return 'process'
        
        # Policy questions
        policy_keywords = ['policy', 'rule', 'guideline', 'regulation', 'compliance', 'allowed']
        if any(keyword in question for keyword in policy_keywords):
            return 'policy'
        
        # Data questions
        data_keywords = ['data', 'report', 'export', 'download', 'backup', 'database']
        if any(keyword in question for keyword in data_keywords):
            return 'data'
        
        # Greeting
        greeting_keywords = ['hello', 'hi', 'help', 'assist', 'support']
        if any(keyword in question for keyword in greeting_keywords):
            return 'greeting'
        
        return 'fallback'
    
    def check_version_context(self, question: str, context: Optional[Dict]) -> Optional[Dict]:
        """Check if question has been resolved in FAQ or future issues"""
        if not context:
            return None
        
        # First check if there's a resolved FAQ answer
        if 'faq_answer' in context and context['faq_answer']:
            return {
                'response': context['faq_answer'],
                'confidence': 0.95,
                'source': 'faq_database',
                'response_type': 'faq_resolution'
            }
        
        # Then check for version information from future issues
        version_info = context.get('version_info')
        if not version_info:
            return None
        
        # Check if question is asking about same issue
        if 'similar_issues' in context and context['similar_issues']:
            for issue in context['similar_issues']:
                if self.similar_question(question, issue.get('question', '')):
                    return {
                        'response': f"This issue has been rectified in version {version_info}.",
                        'confidence': 0.9,
                        'source': 'version_context',
                        'response_type': 'version_resolution',
                        'version_info': version_info
                    }
        
        return None
    
    def similar_question(self, q1: str, q2: str, threshold: float = 0.8) -> bool:
        """Simple similarity check between two questions"""
        if not q1 or not q2:
            return False
        
        # Normalize questions
        q1_words = set(q1.lower().split())
        q2_words = set(q2.lower().split())
        
        # Calculate Jaccard similarity
        intersection = len(q1_words.intersection(q2_words))
        union = len(q1_words.union(q2_words))
        
        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold
    
    def add_context_to_response(self, response: str, context: Dict) -> str:
        """Add relevant context information to response"""
        if not context:
            return response
        
        context_additions = []
        
        # Add user information
        if 'user_role' in context:
            context_additions.append(f"As a {context['user_role']},")
        
        # Add state information
        if 'state_name' in context:
            context_additions.append(f"for {context['state_name']},")
        
        # Add department information
        if 'department' in context:
            context_additions.append(f"the {context['department']} can assist you.")
        
        if context_additions:
            return f"{response} {' '.join(context_additions)}"
        
        return response
    
    def learn_from_interaction(self, question: str, response: str, feedback: Optional[str] = None):
        """Learn from user interactions to improve future responses"""
        try:
            # Load existing learning data
            learning_data = self.load_learning_data()
            
            # Add new interaction
            interaction = {
                'question': question,
                'response': response,
                'feedback': feedback,
                'timestamp': datetime.utcnow().isoformat(),
                'success': feedback is None or 'helpful' in feedback.lower()
            }
            
            learning_data['interactions'].append(interaction)
            
            # Keep only last 1000 interactions
            if len(learning_data['interactions']) > 1000:
                learning_data['interactions'] = learning_data['interactions'][-1000:]
            
            # Save learning data
            self.save_learning_data(learning_data)
            
        except Exception as e:
            pass  # Learning failure is non-critical
    
    def load_learning_data(self) -> Dict:
        """Load learning data"""
        try:
            learning_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'learning_data.json')
            with open(learning_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
            return {'interactions': []}
    
    def save_learning_data(self, data: Dict):
        """Save learning data"""
        try:
            learning_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'learning_data.json')
            os.makedirs(os.path.dirname(learning_file), exist_ok=True)
            with open(learning_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            pass  # Save failure is non-critical
    
    def get_usage_stats(self) -> Dict:
        """Get usage statistics for monitoring"""
        learning_data = self.load_learning_data()
        interactions = learning_data.get('interactions', [])
        
        if not interactions:
            return {'total_interactions': 0, 'success_rate': 0.0}
        
        total = len(interactions)
        successful = sum(1 for i in interactions if i.get('success', False))
        success_rate = (successful / total) * 100 if total > 0 else 0.0
        
        return {
            'total_interactions': total,
            'success_rate': round(success_rate, 2),
            'last_interaction': interactions[-1]['timestamp'] if interactions else None
        }
    
    def suggest_improvements(self, question: str, current_response: str) -> List[Dict]:
        """Suggest improvements for current response"""
        suggestions = []
        
        # Simple improvement suggestions
        if len(current_response.split()) < 10:
            suggestions.append({
                'type': 'length_improvement',
                'suggestion': 'Consider providing more detailed information',
                'confidence': 0.6
            })
        
        if not any(word in current_response.lower() for word in ['please', 'thank you']):
            suggestions.append({
                'type': 'tone_improvement',
                'suggestion': 'Consider adding polite language',
                'confidence': 0.5
            })
        
        return suggestions
    
    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict]:
        """Search local knowledge base"""
        # Simple keyword-based search
        knowledge_data = self.load_knowledge_data()
        query_words = set(query.lower().split())
        
        matches = []
        for entry in knowledge_data.get('entries', []):
            entry_text = f"{entry.get('question', '')} {entry.get('answer', '')} {entry.get('keywords', [])}".lower()
            
            # Calculate relevance score
            score = 0
            for word in query_words:
                if word in entry_text:
                    score += 1
            
            if score > 0:
                matches.append({
                    'entry': entry,
                    'score': score,
                    'relevance': 'high' if score >= 3 else 'medium'
                })
        
        # Sort by score and limit
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches[:limit]
    
    def load_knowledge_data(self) -> Dict:
        """Load knowledge base data"""
        try:
            knowledge_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'knowledge_base.json')
            with open(knowledge_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            return {'entries': []}
    
    def add_knowledge_entry(self, question: str, answer: str, category: str, keywords: List[str], version: str) -> Optional[Dict]:
        """Add entry to local knowledge base"""
        try:
            knowledge_data = self.load_knowledge_data()
            
            entry = {
                'id': len(knowledge_data.get('entries', [])) + 1,
                'question': question,
                'answer': answer,
                'category': category,
                'keywords': keywords,
                'version': version,
                'created_at': datetime.utcnow().isoformat(),
                'last_updated': datetime.utcnow().isoformat(),
                'access_count': 0,
                'quality_score': 0.0
            }
            
            knowledge_data['entries'].append(entry)
            self.save_knowledge_data(knowledge_data)
            
            return entry
            
        except Exception as e:
            return None
    
    def save_knowledge_data(self, data: Dict):
        """Save knowledge base data"""
        try:
            knowledge_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'knowledge_base.json')
            os.makedirs(os.path.dirname(knowledge_file), exist_ok=True)
            with open(knowledge_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            pass  # Save failure is non-critical
    
    def categorize_query(self, question: str) -> Dict:
        """Categorize query into predefined categories"""
        question_lower = question.lower()
        
        # Simple categorization logic
        categories = {
            'Technical': ['error', 'bug', 'issue', 'problem', 'not working'],
            'Process': ['how to', 'procedure', 'process', 'workflow', 'steps'],
            'Policy': ['policy', 'rule', 'guideline', 'regulation', 'compliance'],
            'Data': ['data', 'report', 'export', 'download', 'database'],
            'Version': ['version', 'v1', 'v2', 'v3', 'fixed', 'rectified']
        }
        
        best_category = 'Other'
        best_score = 0
        
        for category, keywords in categories.items():
            score = sum(1 for keyword in keywords if keyword in question_lower)
            if score > best_score:
                best_score = score
                best_category = category
        
        department_mapping = {
            'Technical': 'IT Support Team',
            'Process': 'Process Improvement Team', 
            'Policy': 'Policy Team',
            'Data': 'Data Management Team',
            'Version': 'Development Team',
            'Other': 'General Support'
        }
        
        return {
            'category': best_category,
            'confidence': min(best_score * 0.2, 1.0),
            'suggested_department': department_mapping.get(best_category, 'General Support')
        }
