
"""
Application-level vector support for pgvector
This provides vector operations even when PostgreSQL vector type isn't available
"""
import struct
import numpy as np
from typing import List, Optional, Union

def serialize_vector(vector: List[float]) -> bytes:
    """Serialize a vector to bytes for storage in bytea column"""
    if vector is None or len(vector) == 0:
        return b''
    
    # Convert to numpy array and ensure float32
    np_vector = np.array(vector, dtype=np.float32)
    
    # Serialize as binary data
    return np_vector.tobytes()

def deserialize_vector(byte_data: bytes) -> List[float]:
    """Deserialize bytes back to vector"""
    if not byte_data:
        return []
    
    # Convert bytes to numpy array
    np_vector = np.frombuffer(byte_data, dtype=np.float32)
    
    # Convert to list
    return np_vector.tolist()

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    if vec1 is None or vec2 is None or len(vec1) == 0 or len(vec2) == 0 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)

def l2_distance(vec1: List[float], vec2: List[float]) -> float:
    """Calculate L2 distance between two vectors"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return float('inf')
    
    return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5

def validate_vector(vector: List[float], expected_size: int = 384) -> bool:
    """Validate vector dimensions"""
    return isinstance(vector, list) and len(vector) == expected_size

def normalize_vector(vector: List[float]) -> List[float]:
    """Normalize vector to unit length"""
    if not vector:
        return vector
    
    magnitude = sum(x * x for x in vector) ** 0.5
    if magnitude == 0:
        return vector
    
    return [x / magnitude for x in vector]
