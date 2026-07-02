import numpy as np
from typing import List, Dict, Tuple, Optional
from sqlalchemy import text, and_, or_
from sentence_transformers import SentenceTransformer
from flask import current_app

from ..document_qa_models import QADocumentChunk, SecureDocument, DocumentStatus


class VectorStoreService:
    """Vector storage service using pgvector for similarity search"""
    
    def __init__(self):
        """Initialize the vector store service"""
        self.embedding_dimension = 384  # MiniLM-L6-v2 dimension
        self.similarity_threshold = float(current_app.config.get('SIMILARITY_THRESHOLD', 0.72))
        self.top_k_chunks = int(current_app.config.get('TOP_K_CHUNKS', 5))
        
        # Lazy loading of embedding model
        self._embedding_model = None
    
    @property
    def embedding_model(self):
        """Lazy loading of embedding model"""
        if self._embedding_model is None:
            model_name = current_app.config.get('EMBEDDING_MODEL_NAME', 'sentence-transformers/all-MiniLM-L6-v2')
            self._embedding_model = SentenceTransformer(model_name)
        return self._embedding_model
    
    def embed_query(self, query_text: str) -> List[float]:
        """
        Generate embedding for query text
        
        Args:
            query_text: Query text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            embedding = self.embedding_model.encode(
                query_text,
                normalize_embeddings=True
            )
            return embedding.tolist()
        except Exception as e:
            current_app.logger.error(f"Error generating query embedding: {e}")
            # Return zero embedding as fallback
            return [0.0] * self.embedding_dimension
    
    def similarity_search(self, user_id: int, query_embedding: List[float], 
                         top_k: int = None, similarity_threshold: float = None,
                         include_flagged: bool = False) -> List[Dict]:
        """
        Perform similarity search across user's document chunks
        
        Args:
            user_id: User ID to scope search
            query_embedding: Query embedding vector
            top_k: Number of results to return
            similarity_threshold: Minimum similarity threshold
            include_flagged: Whether to include flagged chunks
            
        Returns:
            List of similar chunks with metadata
        """
        if top_k is None:
            top_k = self.top_k_chunks
        if similarity_threshold is None:
            similarity_threshold = self.similarity_threshold
        
        try:
            # Build query conditions
            conditions = [DocumentChunk.user_id == user_id]
            
            if not include_flagged:
                conditions.append(DocumentChunk.flagged == False)
            
            # Use pgvector's <=> operator for cosine similarity
            # Note: pgvector uses distance, so we need to convert similarity to distance
            # distance = 1 - similarity
            max_distance = 1 - similarity_threshold
            
            query_str = f"""
            SELECT 
                dc.id,
                dc.document_id,
                dc.chunk_index,
                dc.chunk_text,
                dc.chunk_type,
                dc.created_at,
                d.original_filename,
                d.stored_filename,
                (1 - (dc.embedding <=> :query_vector)) as similarity
            FROM qa_document_chunks dc
            JOIN secure_documents d ON dc.document_id = d.id
            WHERE dc.user_id = :user_id
            AND d.deleted_at IS NULL
            AND (dc.embedding <=> :query_vector) <= :max_distance
            ORDER BY similarity DESC
            LIMIT :limit
            """
            
            from .. import db
            
            result = db.session.execute(
                text(query_str),
                {
                    'query_vector': query_embedding,
                    'user_id': user_id,
                    'max_distance': max_distance,
                    'limit': top_k
                }
            )
            
            chunks = []
            for row in result:
                chunks.append({
                    'id': row.id,
                    'document_id': row.document_id,
                    'chunk_index': row.chunk_index,
                    'chunk_text': row.chunk_text,
                    'chunk_type': row.chunk_type,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'original_filename': row.original_filename,
                    'stored_filename': row.stored_filename,
                    'similarity': float(row.similarity)
                })
            
            return chunks
            
        except Exception as e:
            current_app.logger.error(f"Error in similarity search: {e}")
            return []
    
    def hybrid_search(self, user_id: int, query_text: str, 
                     top_k: int = None, similarity_threshold: float = None,
                     include_flagged: bool = False) -> List[Dict]:
        """
        Hybrid search combining semantic similarity with keyword matching
        
        Args:
            user_id: User ID to scope search
            query_text: Query text
            top_k: Number of results to return
            similarity_threshold: Minimum similarity threshold
            include_flagged: Whether to include flagged chunks
            
        Returns:
            List of similar chunks with hybrid scores
        """
        # Generate query embedding
        query_embedding = self.embed_query(query_text)
        
        # Perform semantic search
        semantic_results = self.similarity_search(
            user_id, query_embedding, top_k * 2, similarity_threshold, include_flagged
        )
        
        # Perform keyword search for additional context
        keyword_results = self._keyword_search(user_id, query_text, include_flagged)
        
        # Combine and deduplicate results
        combined_results = self._combine_search_results(semantic_results, keyword_results)
        
        # Return top_k results
        return combined_results[:top_k or self.top_k_chunks]
    
    def _keyword_search(self, user_id: int, query_text: str, 
                       include_flagged: bool = False) -> List[Dict]:
        """
        Simple keyword search using PostgreSQL text search
        
        Args:
            user_id: User ID to scope search
            query_text: Query text
            include_flagged: Whether to include flagged chunks
            
        Returns:
            List of chunks matching keywords
        """
        try:
            # Use PostgreSQL's full-text search
            query_str = f"""
            SELECT 
                dc.id,
                dc.document_id,
                dc.chunk_index,
                dc.chunk_text,
                dc.chunk_type,
                dc.created_at,
                d.original_filename,
                d.stored_filename,
                ts_rank_cd(to_tsvector('english', dc.chunk_text), 
                          plainto_tsquery('english', :query_text)) as rank
            FROM qa_document_chunks dc
            JOIN secure_documents d ON dc.document_id = d.id
            WHERE dc.user_id = :user_id
            AND d.deleted_at IS NULL
            AND to_tsvector('english', dc.chunk_text) @@ plainto_tsquery('english', :query_text)
            ORDER BY rank DESC
            LIMIT 20
            """
            
            from .. import db
            
            result = db.session.execute(
                text(query_str),
                {
                    'query_text': query_text,
                    'user_id': user_id
                }
            )
            
            chunks = []
            for row in result:
                chunks.append({
                    'id': row.id,
                    'document_id': row.document_id,
                    'chunk_index': row.chunk_index,
                    'chunk_text': row.chunk_text,
                    'chunk_type': row.chunk_type,
                    'created_at': row.created_at.isoformat() if row.created_at else None,
                    'original_filename': row.original_filename,
                    'stored_filename': row.stored_filename,
                    'similarity': float(row.rank) * 0.5,  # Scale keyword rank
                    'search_type': 'keyword'
                })
            
            return chunks
            
        except Exception as e:
            current_app.logger.error(f"Error in keyword search: {e}")
            return []
    
    def _combine_search_results(self, semantic_results: List[Dict], 
                              keyword_results: List[Dict]) -> List[Dict]:
        """
        Combine semantic and keyword search results
        
        Args:
            semantic_results: Results from semantic search
            keyword_results: Results from keyword search
            
        Returns:
            Combined and deduplicated results
        """
        # Create a dictionary to deduplicate by chunk ID
        combined = {}
        
        # Add semantic results
        for result in semantic_results:
            result['search_type'] = 'semantic'
            combined[result['id']] = result
        
        # Add keyword results, updating scores if already present
        for result in keyword_results:
            chunk_id = result['id']
            if chunk_id in combined:
                # Boost score for chunks that appear in both searches
                combined[chunk_id]['similarity'] = min(
                    combined[chunk_id]['similarity'] + result['similarity'] * 0.3,
                    1.0
                )
                combined[chunk_id]['search_type'] = 'hybrid'
            else:
                combined[chunk_id] = result
        
        # Sort by similarity score
        return sorted(combined.values(), key=lambda x: x['similarity'], reverse=True)
    
    def get_document_chunks_by_ids(self, user_id: int, chunk_ids: List[str]) -> List[Dict]:
        """
        Get specific chunks by their IDs
        
        Args:
            user_id: User ID for validation
            chunk_ids: List of chunk IDs to retrieve
            
        Returns:
            List of chunk dictionaries
        """
        try:
            chunks = QADocumentChunk.query.filter(
                and_(
                    QADocumentChunk.user_id == user_id,
                    QADocumentChunk.id.in_(chunk_ids)
                )
            ).all()
            
            result = []
            for chunk in chunks:
                result.append({
                    'id': chunk.id,
                    'document_id': chunk.document_id,
                    'chunk_index': chunk.chunk_index,
                    'chunk_text': chunk.chunk_text,
                    'chunk_type': chunk.chunk_type,
                    'created_at': chunk.created_at.isoformat() if chunk.created_at else None,
                    'original_filename': chunk.document.original_filename if chunk.document else None
                })
            
            return result
            
        except Exception as e:
            current_app.logger.error(f"Error getting chunks by IDs: {e}")
            return []
    
    def search_by_document(self, user_id: int, document_id: str, 
                           query_text: str = None) -> List[Dict]:
        """
        Search within a specific document
        
        Args:
            user_id: User ID for validation
            document_id: Document ID to search within
            query_text: Optional query text for filtering
            
        Returns:
            List of chunks from the specified document
        """
        try:
            # Validate document ownership
            document = SecureDocument.query.filter_by(
                id=document_id,
                user_id=user_id
            ).filter(SecureDocument.deleted_at.is_(None)).first()
            
            if not document:
                return []
            
            query = QADocumentChunk.query.filter_by(
                document_id=document_id,
                user_id=user_id
            )
            
            # If query text provided, filter by keywords
            if query_text:
                query = query.filter(
                    QADocumentChunk.chunk_text.ilike(f'%{query_text}%')
                )
            
            chunks = query.order_by(QADocumentChunk.chunk_index).all()
            
            result = []
            for chunk in chunks:
                result.append({
                    'id': chunk.id,
                    'document_id': chunk.document_id,
                    'chunk_index': chunk.chunk_index,
                    'chunk_text': chunk.chunk_text,
                    'chunk_type': chunk.chunk_type,
                    'created_at': chunk.created_at.isoformat() if chunk.created_at else None,
                    'original_filename': document.original_filename
                })
            
            return result
            
        except Exception as e:
            current_app.logger.error(f"Error searching by document: {e}")
            return []
    
    def get_user_statistics(self, user_id: int) -> Dict:
        """
        Get statistics for a user's documents
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with usage statistics
        """
        try:
            from sqlalchemy import func
            
            # Document statistics
            doc_stats = db.session.query(
                func.count(SecureDocument.id).label('total_documents'),
                func.sum(SecureDocument.file_size).label('total_size')
            ).filter_by(
                user_id=user_id
            ).filter(SecureDocument.deleted_at.is_(None)).first()
            
            # Chunk statistics
            chunk_stats = db.session.query(
                func.count(QADocumentChunk.id).label('total_chunks')
            ).filter_by(user_id=user_id).first()
            
            return {
                'total_documents': doc_stats.total_documents or 0,
                'total_size_bytes': doc_stats.total_size or 0,
                'total_chunks': chunk_stats.total_chunks or 0,
                'total_tokens': 0,
                'flagged_chunks': 0,
                'average_chunks_per_document': (
                    (chunk_stats.total_chunks or 0) / (doc_stats.total_documents or 1)
                )
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting user statistics: {e}")
            return {
                'total_documents': 0,
                'total_size_bytes': 0,
                'total_chunks': 0,
                'total_tokens': 0,
                'flagged_chunks': 0,
                'average_chunks_per_document': 0
            }
    
    def create_index(self) -> bool:
        """
        Create necessary indexes for vector search performance
        
        Returns:
            True if successful, False otherwise
        """
        try:
            from .. import db
            
            # Create vector index for similarity search
            index_queries = [
                # Vector similarity index
                """
                CREATE INDEX IF NOT EXISTS idx_qa_document_chunks_embedding 
                ON qa_document_chunks 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """,
                
                # Composite indexes for common queries
                """
                CREATE INDEX IF NOT EXISTS idx_qa_document_chunks_document_user 
                ON qa_document_chunks (document_id, user_id)
                """,
                
                # Full-text search index
                """
                CREATE INDEX IF NOT EXISTS idx_qa_document_chunks_text_search 
                ON qa_document_chunks 
                USING gin(to_tsvector('english', chunk_text))
                """
            ]
            
            for query in index_queries:
                db.session.execute(text(query))
            
            db.session.commit()
            return True
            
        except Exception as e:
            current_app.logger.error(f"Error creating vector indexes: {e}")
            from .. import db
            db.session.rollback()
            return False
