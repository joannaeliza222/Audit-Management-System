
"""
Vector search functionality for bytea-stored embeddings
"""
import numpy as np
from app.utils.vector_support import deserialize_vector, cosine_similarity, l2_distance
from app.models import FAQ
from app import db

def vector_search(query_embedding: list, limit: int = 10, similarity_threshold: float = 0.7):
    """
    Search for similar FAQs using vector similarity
    Works with bytea-stored embeddings
    """
    if not query_embedding:
        return []
    
    # Get all FAQs with embeddings
    faqs = FAQ.query.filter(FAQ.embedding.isnot(None)).all()
    
    results = []
    for faq in faqs:
        if faq.embedding:
            # Deserialize stored embedding
            stored_embedding = deserialize_vector(faq.embedding)
            
            if stored_embedding:
                # Calculate similarity
                similarity = cosine_similarity(query_embedding, stored_embedding)
                
                if similarity >= similarity_threshold:
                    results.append({
                        'faq': faq,
                        'similarity': similarity,
                        'distance': l2_distance(query_embedding, stored_embedding)
                    })
    
    # Sort by similarity (descending)
    results.sort(key=lambda x: x['similarity'], reverse=True)
    
    return results[:limit]

def find_similar_faqs(question: str, limit: int = 5):
    """
    Find similar FAQs for a given question
    """
    from app.utils.embeddings import get_bert_embeddings, normalize
    
    # Generate embedding for the question
    embedding = get_bert_embeddings(question)
    if embedding:
        normalized_embedding = normalize(embedding) if hasattr(embedding, 'tolist') else embedding
        return vector_search(normalized_embedding, limit)
    
    return []
