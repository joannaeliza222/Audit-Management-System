"""
Natural Language to Database Query Service
Secure local AI system for converting natural language to database queries
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, text, desc, extract, asc
from flask import current_app, has_app_context
from app import db
from app.models import FAQ, User, Logs, DataDump, DraftFAQ
from app.audit_models import AuditQuery, Commitment


class NaturalLanguageDB:
    """Secure natural language to database query converter"""
    
    def __init__(self):
        self.db_schema = self._load_database_schema()
        self.query_patterns = self._load_query_patterns()
        self.security_filters = self._load_security_filters()
    
    def _load_database_schema(self) -> Dict:
        """Load database schema information for AI understanding"""
        return {
            "tables": {
                "FAQ": {
                    "description": "Frequently Asked Questions database",
                    "columns": {
                        "id": {"type": "integer", "description": "Unique identifier"},
                        "question": {"type": "text", "description": "The question text"},
                        "answer": {"type": "text", "description": "The answer text"},
                        "state_name": {"type": "string", "description": "State name"},
                        "category": {"type": "string", "description": "Question category"},
                        "created_at": {"type": "datetime", "description": "Creation timestamp"},
                        "updated_at": {"type": "datetime", "description": "Last update timestamp"}
                    },
                    "common_queries": ["count", "by_state", "by_category", "recent", "search"]
                },
                "User": {
                    "description": "User accounts and roles",
                    "columns": {
                        "id": {"type": "integer", "description": "Unique identifier"},
                        "username": {"type": "string", "description": "Username"},
                        "email": {"type": "string", "description": "Email address"},
                        "role": {"type": "string", "description": "User role (admin, reviewer, modifier, viewer)"},
                        "state_name": {"type": "string", "description": "State name"},
                        "created_at": {"type": "datetime", "description": "Account creation timestamp"}
                    },
                    "common_queries": ["count", "by_role", "by_state", "recent", "active"]
                },
                "DataDump": {
                    "description": "Data dump requests and tracking",
                    "columns": {
                        "id": {"type": "integer", "description": "Unique identifier"},
                        "request_date": {"type": "datetime", "description": "When the request was made"},
                        "share_date": {"type": "datetime", "description": "When data was shared"},
                        "state": {"type": "string", "description": "State name"},
                        "coordinator_name": {"type": "string", "description": "Coordinator name"},
                        "coordinator": {"type": "string", "description": "Coordinator email"},
                        "status": {"type": "string", "description": "Request status"},
                        "data_type": {"type": "string", "description": "Type of data requested"}
                    },
                    "common_queries": ["count", "pending", "completed", "by_state", "processing_time", "recent"]
                },
                "AuditQuery": {
                    "description": "Audit query management",
                    "columns": {
                        "id": {"type": "integer", "description": "Unique identifier"},
                        "subject": {"type": "text", "description": "Query subject"},
                        "query_details": {"type": "text", "description": "Detailed query description"},
                        "state": {"type": "string", "description": "State name"},
                        "status": {"type": "string", "description": "Query status"},
                        "priority": {"type": "string", "description": "Query priority"},
                        "query_date": {"type": "datetime", "description": "When query was created"},
                        "created_by": {"type": "string", "description": "Who created the query"}
                    },
                    "common_queries": ["count", "by_state", "by_status", "by_priority", "recent", "pending"]
                },
                "Commitment": {
                    "description": "Commitments made in responses",
                    "columns": {
                        "id": {"type": "integer", "description": "Unique identifier"},
                        "query_id": {"type": "integer", "description": "Related query ID"},
                        "commitment_text": {"type": "text", "description": "Commitment description"},
                        "deadline": {"type": "datetime", "description": "Commitment deadline"},
                        "status": {"type": "string", "description": "Commitment status"},
                        "responsible": {"type": "string", "description": "Responsible person"}
                    },
                    "common_queries": ["count", "overdue", "upcoming", "by_status", "by_responsible"]
                },
                "DraftFAQ": {
                    "description": "Draft FAQs awaiting review",
                    "columns": {
                        "id": {"type": "integer", "description": "Unique identifier"},
                        "question": {"type": "text", "description": "Question text"},
                        "answer": {"type": "text", "description": "Answer text"},
                        "state_name": {"type": "string", "description": "State name"},
                        "status": {"type": "string", "description": "Draft status (pending, approved, rejected)"},
                        "created_by": {"type": "string", "description": "Who created the draft"},
                        "created_at": {"type": "datetime", "description": "Creation timestamp"}
                    },
                    "common_queries": ["count", "pending", "by_state", "by_status", "recent"]
                }
            },
            "relationships": {
                "AuditQuery -> Commitment": "one-to-many via query_id",
                "User -> AuditQuery": "one-to-many via created_by",
                "User -> DraftFAQ": "one-to-many via created_by"
            }
        }
    
    def _load_query_patterns(self) -> Dict:
        """Load natural language patterns for query understanding"""
        return {
            "count_patterns": [
                r"how many\s+(\w+)",
                r"number of\s+(\w+)",
                r"total\s+(\w+)",
                r"count\s+of\s+(\w+)",
                r"(\w+)\s+count",
                r"total\s+(\w+)\s+in\s+(\w+)"
            ],
            "state_patterns": [
                r"in\s+(\w+)\s+state",
                r"for\s+(\w+)\s+state",
                r"(\w+)\s+state",
                r"from\s+(\w+)"
            ],
            "time_patterns": [
                r"last\s+(\d+)\s+days",
                r"past\s+(\d+)\s+days",
                r"recent",
                r"this\s+month",
                r"last\s+month",
                r"this\s+year",
                r"overdue",
                r"upcoming"
            ],
            "status_patterns": [
                r"pending",
                r"completed",
                r"approved",
                r"rejected",
                r"active",
                r"inactive",
                r"overdue"
            ],
            "comparison_patterns": [
                r"compare\s+(\w+)\s+and\s+(\w+)",
                r"(\w+)\s+vs\s+(\w+)",
                r"which\s+state\s+has",
                r"top\s+(\d+)\s+states",
                r"highest",
                r"lowest"
            ]
        }
    
    def _load_security_filters(self) -> Dict:
        """Load security filters for query validation"""
        return {
            "allowed_operations": ["SELECT", "COUNT", "SUM", "AVG", "MAX", "MIN"],
            "forbidden_keywords": ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "CREATE"],
            "allowed_tables": list(self.db_schema["tables"].keys()),
            "max_limit": 1000,
            "timeout_seconds": 30
        }
    
    def understand_query(self, natural_query: str, user_role: str = "viewer") -> Dict:
        """
        Understand natural language query and convert to structured database query
        
        Args:
            natural_query: User's natural language question
            user_role: User's role for access control
            
        Returns:
            Dict containing query plan and results
        """
        try:
            # Check if we have Flask application context
            if not has_app_context():
                return {
                    "error": "Database access is not available in the current context. Please try again.",
                    "query_type": "context_error",
                    "suggestion": "The system may be restarting. Please wait a moment and try again."
                }
            
            # Parse the natural language query
            parsed_query = self._parse_natural_language(natural_query)
            
            # Validate query security
            if not self._validate_query_security(parsed_query, user_role):
                return {
                    "error": "Query not authorized for your role",
                    "query_type": "unauthorized",
                    "suggestion": "Please contact your administrator for access"
                }
            
            # Generate and execute database query
            result = self._execute_query(parsed_query)
            
            # Generate natural language response
            response = self._generate_natural_response(natural_query, parsed_query, result)
            
            return {
                "response": response,
                "data": result,
                "query_type": parsed_query.get("type", "unknown"),
                "confidence": self._calculate_confidence(parsed_query, result),
                "sources": self._get_data_sources(parsed_query)
            }
            
        except Exception as e:
            # Log error safely without using current_app
            import logging
            logging.error(f"Error processing natural language query: {str(e)}")
            return {
                "error": "I couldn't understand your question. Please try rephrasing it.",
                "query_type": "error",
                "suggestion": "Try asking about counts, comparisons, or specific information"
            }
    
    def _parse_natural_language(self, query: str) -> Dict:
        """Parse natural language query into structured components"""
        query_lower = query.lower().strip()
        
        parsed = {
            "original": query,
            "type": "unknown",
            "table": None,
            "operation": None,
            "conditions": {},
            "aggregations": [],
            "order": None,
            "limit": None
        }
        
        # Identify query type and table
        if any(pattern in query_lower for pattern in ["how many", "number of", "total", "count"]):
            parsed["type"] = "count"
            parsed["operation"] = "COUNT"
        
        elif any(pattern in query_lower for pattern in ["compare", "vs", "which", "top", "highest", "lowest"]):
            parsed["type"] = "comparison"
            parsed["operation"] = "COMPARE"
        
        elif any(pattern in query_lower for pattern in ["show", "list", "display", "what", "tell me"]):
            parsed["type"] = "list"
            parsed["operation"] = "SELECT"
        
        # Identify target table
        for table_name, table_info in self.db_schema["tables"].items():
            keywords = [table_name.lower()] + [col.lower() for col in table_info["columns"].keys()]
            if any(keyword in query_lower for keyword in keywords):
                parsed["table"] = table_name
                break
        
        # Extract conditions
        parsed["conditions"] = self._extract_conditions(query_lower)
        
        # Extract aggregations
        parsed["aggregations"] = self._extract_aggregations(query_lower)
        
        # Extract ordering
        parsed["order"] = self._extract_ordering(query_lower)
        
        # Extract limit
        parsed["limit"] = self._extract_limit(query_lower)
        
        return parsed
    
    def _extract_conditions(self, query: str) -> Dict:
        """Extract conditions from natural language query"""
        conditions = {}
        
        # State conditions
        for pattern in self.query_patterns["state_patterns"]:
            match = re.search(pattern, query)
            if match:
                conditions["state"] = match.group(1).title()
                break
        
        # Status conditions
        for pattern in self.query_patterns["status_patterns"]:
            if pattern in query:
                conditions["status"] = pattern
                break
        
        # Time conditions
        for pattern in self.query_patterns["time_patterns"]:
            match = re.search(pattern, query)
            if match:
                if "days" in pattern:
                    conditions["time_range"] = int(match.group(1))
                else:
                    conditions["time_keyword"] = pattern
                break
        
        return conditions
    
    def _extract_aggregations(self, query: str) -> List[str]:
        """Extract aggregation requirements from query"""
        aggregations = []
        
        if any(word in query for word in ["average", "avg"]):
            aggregations.append("AVG")
        if any(word in query for word in ["sum", "total"]):
            aggregations.append("SUM")
        if any(word in query for word in ["maximum", "max", "highest"]):
            aggregations.append("MAX")
        if any(word in query for word in ["minimum", "min", "lowest"]):
            aggregations.append("MIN")
        
        return aggregations
    
    def _extract_ordering(self, query: str) -> Optional[str]:
        """Extract ordering requirements from query"""
        if "highest" in query or "most" in query or "top" in query:
            return "DESC"
        elif "lowest" in query or "least" in query or "bottom" in query:
            return "ASC"
        return None
    
    def _extract_limit(self, query: str) -> Optional[int]:
        """Extract limit from query"""
        match = re.search(r"top\s+(\d+)", query)
        if match:
            return int(match.group(1))
        return None
    
    def _validate_query_security(self, parsed_query: Dict, user_role: str) -> bool:
        """Validate query security based on user role"""
        # Role-based access control
        role_permissions = {
            "viewer": ["FAQ"],
            "modifier": ["FAQ", "AuditQuery"],
            "reviewer": ["FAQ", "AuditQuery", "DraftFAQ"],
            "admin": ["FAQ", "User", "DataDump", "AuditQuery", "Commitment", "DraftFAQ"]
        }
        
        user_permissions = role_permissions.get(user_role, [])
        table = parsed_query.get("table")
        
        if table and table not in user_permissions:
            return False
        
        # Check operation security
        operation = parsed_query.get("operation")
        if operation and operation not in self.security_filters["allowed_operations"]:
            return False
        
        return True
    
    def _execute_query(self, parsed_query: Dict) -> Dict:
        """Execute the parsed database query"""
        table = parsed_query.get("table")
        if not table:
            return {"error": "Could not determine target table"}
        
        try:
            if table == "FAQ":
                return self._execute_faq_query(parsed_query)
            elif table == "User":
                return self._execute_user_query(parsed_query)
            elif table == "DataDump":
                return self._execute_datadump_query(parsed_query)
            elif table == "AuditQuery":
                return self._execute_audit_query(parsed_query)
            elif table == "Commitment":
                return self._execute_commitment_query(parsed_query)
            elif table == "DraftFAQ":
                return self._execute_draft_faq_query(parsed_query)
            else:
                return {"error": f"Unsupported table: {table}"}
                
        except Exception as e:
            import logging
            logging.error(f"Query execution error: {str(e)}")
            return {"error": "Failed to execute database query"}
    
    def _execute_faq_query(self, parsed_query: Dict) -> Dict:
        """Execute FAQ-related queries"""
        # Check Flask context
        if not has_app_context():
            return {"error": "Database context not available"}
            
        conditions = parsed_query.get("conditions", {})
        operation = parsed_query.get("operation", "SELECT")
        
        try:
            if operation == "COUNT":
                query = db.session.query(func.count(FAQ.id))
                
                # Apply filters
                if "state" in conditions:
                    query = query.filter(FAQ.state_name == conditions["state"])
                
                count = query.scalar()
                return {
                    "count": count,
                    "table": "FAQ",
                    "operation": "COUNT",
                    "filters": conditions
                }
            
            elif operation == "SELECT":
                query = db.session.query(FAQ)
                
                # Apply filters
                if "state" in conditions:
                    query = query.filter(FAQ.state_name == conditions["state"])
                
                # Apply ordering
                if parsed_query.get("order") == "DESC":
                    query = query.order_by(desc(FAQ.created_at))
                else:
                    query = query.order_by(FAQ.created_at)
                
                # Apply limit
                limit = parsed_query.get("limit", 10)
                query = query.limit(limit)
                
                results = query.all()
                return {
                    "results": [{"id": r.id, "question": r.question, "state": r.state_name, "created_at": r.created_at} for r in results],
                    "count": len(results),
                    "table": "FAQ",
                    "operation": "SELECT"
                }
            
            return {"error": "Unsupported operation for FAQ"}
            
        except Exception as e:
            import logging
            logging.error(f"FAQ query execution error: {str(e)}")
            return {"error": "Failed to execute FAQ query"}
    
    def _execute_datadump_query(self, parsed_query: Dict) -> Dict:
        """Execute DataDump-related queries"""
        # Check Flask context
        if not has_app_context():
            return {"error": "Database context not available"}
            
        conditions = parsed_query.get("conditions", {})
        operation = parsed_query.get("operation", "SELECT")
        
        try:
            if operation == "COUNT":
                query = db.session.query(func.count(DataDump.id))
                
                # Apply filters
                if "state" in conditions:
                    query = query.filter(DataDump.state == conditions["state"])
                
                if "status" in conditions:
                    if conditions["status"] == "pending":
                        query = query.filter(DataDump.share_date.is_(None))
                    elif conditions["status"] == "completed":
                        query = query.filter(DataDump.share_date.isnot(None))
                
                count = query.scalar()
                return {
                    "count": count,
                    "table": "DataDump",
                    "operation": "COUNT",
                    "filters": conditions
                }
            
            elif operation == "SELECT":
                query = db.session.query(DataDump)
                
                # Apply filters
                if "state" in conditions:
                    query = query.filter(DataDump.state == conditions["state"])
                
                # Apply ordering
                if parsed_query.get("order") == "DESC":
                    query = query.order_by(desc(DataDump.request_date))
                else:
                    query = query.order_by(DataDump.request_date)
                
                # Apply limit
                limit = parsed_query.get("limit", 10)
                query = query.limit(limit)
                
                results = query.all()
                return {
                    "results": [{
                        "id": r.id, 
                        "state": r.state, 
                        "coordinator": r.coordinator_name,
                        "request_date": r.request_date,
                        "share_date": r.share_date
                    } for r in results],
                    "count": len(results),
                    "table": "DataDump",
                    "operation": "SELECT"
                }
            
            return {"error": "Unsupported operation for DataDump"}
            
        except Exception as e:
            import logging
            logging.error(f"DataDump query execution error: {str(e)}")
            return {"error": "Failed to execute DataDump query"}
    
    def _execute_audit_query(self, parsed_query: Dict) -> Dict:
        """Execute AuditQuery-related queries"""
        conditions = parsed_query.get("conditions", {})
        operation = parsed_query.get("operation", "SELECT")
        
        if operation == "COUNT":
            query = db.session.query(func.count(AuditQuery.id))
            
            # Apply filters
            if "state" in conditions:
                query = query.filter(AuditQuery.state == conditions["state"])
            
            if "status" in conditions:
                query = query.filter(AuditQuery.status == conditions["status"])
            
            count = query.scalar()
            return {
                "count": count,
                "table": "AuditQuery",
                "operation": "COUNT",
                "filters": conditions
            }
        
        elif operation == "SELECT":
            query = db.session.query(AuditQuery)
            
            # Apply filters
            if "state" in conditions:
                query = query.filter(AuditQuery.state == conditions["state"])
            
            # Apply ordering
            if parsed_query.get("order") == "DESC":
                query = query.order_by(desc(AuditQuery.query_date))
            else:
                query = query.order_by(AuditQuery.query_date)
            
            # Apply limit
            limit = parsed_query.get("limit", 10)
            query = query.limit(limit)
            
            results = query.all()
            return {
                "results": [{
                    "id": r.id, 
                    "subject": r.subject, 
                    "state": r.state,
                    "status": r.status,
                    "priority": r.priority,
                    "query_date": r.query_date
                } for r in results],
                "count": len(results),
                "table": "AuditQuery",
                "operation": "SELECT"
            }
        
        return {"error": "Unsupported operation for AuditQuery"}
    
    def _execute_user_query(self, parsed_query: Dict) -> Dict:
        """Execute User-related queries"""
        conditions = parsed_query.get("conditions", {})
        operation = parsed_query.get("operation", "SELECT")
        
        if operation == "COUNT":
            query = db.session.query(func.count(User.id))
            
            # Apply filters
            if "state" in conditions:
                query = query.filter(User.state_name == conditions["state"])
            
            if "status" in conditions:
                if conditions["status"] == "active":
                    query = query.filter(User.is_active == True)
            
            count = query.scalar()
            return {
                "count": count,
                "table": "User",
                "operation": "COUNT",
                "filters": conditions
            }
        
        return {"error": "Unsupported operation for User"}
    
    def _execute_commitment_query(self, parsed_query: Dict) -> Dict:
        """Execute Commitment-related queries"""
        conditions = parsed_query.get("conditions", {})
        operation = parsed_query.get("operation", "SELECT")
        
        if operation == "COUNT":
            query = db.session.query(func.count(Commitment.id))
            
            # Apply filters
            if "status" in conditions:
                if conditions["status"] == "overdue":
                    query = query.filter(Commitment.deadline < datetime.utcnow())
                elif conditions["status"] == "upcoming":
                    query = query.filter(
                        Commitment.deadline > datetime.utcnow(),
                        Commitment.deadline <= datetime.utcnow() + timedelta(days=7)
                    )
            
            count = query.scalar()
            return {
                "count": count,
                "table": "Commitment",
                "operation": "COUNT",
                "filters": conditions
            }
        
        return {"error": "Unsupported operation for Commitment"}
    
    def _execute_draft_faq_query(self, parsed_query: Dict) -> Dict:
        """Execute DraftFAQ-related queries"""
        conditions = parsed_query.get("conditions", {})
        operation = parsed_query.get("operation", "SELECT")
        
        if operation == "COUNT":
            query = db.session.query(func.count(DraftFAQ.id))
            
            # Apply filters
            if "state" in conditions:
                query = query.filter(DraftFAQ.state_name == conditions["state"])
            
            if "status" in conditions:
                query = query.filter(DraftFAQ.status == conditions["status"])
            
            count = query.scalar()
            return {
                "count": count,
                "table": "DraftFAQ",
                "operation": "COUNT",
                "filters": conditions
            }
        
        return {"error": "Unsupported operation for DraftFAQ"}
    
    def _generate_natural_response(self, original_query: str, parsed_query: Dict, result: Dict) -> str:
        """Generate natural language response from query results"""
        if "error" in result:
            return f"I'm sorry, I couldn't find that information. {result['error']}"
        
        query_type = parsed_query.get("type", "unknown")
        table = parsed_query.get("table", "")
        conditions = parsed_query.get("conditions", {})
        
        if query_type == "count":
            count = result.get("count", 0)
            table_desc = self.db_schema["tables"].get(table, {}).get("description", table)
            
            # Build natural response
            if "state" in conditions:
                response = f"There are {count} {table_desc.lower()} in {conditions['state']}."
            else:
                response = f"There are {count} {table_desc.lower()} in total."
            
            return response
        
        elif query_type == "list":
            results = result.get("results", [])
            count = len(results)
            
            if count == 0:
                return f"I couldn't find any matching records."
            
            response = f"I found {count} matching records:\n\n"
            for i, item in enumerate(results[:5], 1):  # Show top 5
                if table == "FAQ":
                    response += f"{i}. {item.get('question', 'N/A')} (from {item.get('state', 'Unknown')})\n"
                elif table == "DataDump":
                    response += f"{i}. Request from {item.get('state', 'Unknown')} by {item.get('coordinator', 'N/A')}\n"
                elif table == "AuditQuery":
                    response += f"{i}. {item.get('subject', 'N/A')} from {item.get('state', 'Unknown')} ({item.get('status', 'N/A')})\n"
            
            if count > 5:
                response += f"\n... and {count - 5} more records."
            
            return response
        
        elif query_type == "comparison":
            # Handle comparison queries
            return self._generate_comparison_response(parsed_query, result)
        
        return "I found some information, but I'm not sure how to present it clearly."
    
    def _generate_comparison_response(self, parsed_query: Dict, result: Dict) -> str:
        """Generate response for comparison queries"""
        # This is a simplified version - can be enhanced
        return "I can help you compare data, but this feature needs more development."
    
    def _calculate_confidence(self, parsed_query: Dict, result: Dict) -> float:
        """Calculate confidence score for the query result"""
        confidence = 0.5  # Base confidence
        
        # Increase confidence based on query clarity
        if parsed_query.get("table"):
            confidence += 0.2
        if parsed_query.get("operation"):
            confidence += 0.2
        if result.get("count", 0) > 0:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _get_data_sources(self, parsed_query: Dict) -> List[str]:
        """Get data sources used in the query"""
        table = parsed_query.get("table")
        if table:
            return [f"Database table: {table}"]
        return ["Database"]
