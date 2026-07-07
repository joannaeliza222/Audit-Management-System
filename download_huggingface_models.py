"""
Pre-download HuggingFace models for offline deployment.
Run this script in a connected environment before deploying to air-gapped system.
"""

import os
import sys

# Force offline mode to be disabled for downloading
os.environ.pop('TRANSFORMERS_OFFLINE', None)
os.environ.pop('HF_DATASETS_OFFLINE', None)

from transformers import AutoModel, AutoTokenizer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def download_model():
    """Download model and tokenizer to local cache."""
    print(f"Downloading model: {MODEL_NAME}")
    print("This may take a few minutes depending on your connection...")
    
    try:
        # Download tokenizer
        print("Downloading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        print("✓ Tokenizer downloaded")
        
        # Download model
        print("Downloading model...")
        model = AutoModel.from_pretrained(MODEL_NAME)
        print("✓ Model downloaded")
        
        print("\n" + "="*50)
        print("Download complete!")
        print("="*50)
        print(f"\nModel cache location: {os.path.join(os.path.expanduser('~'), '.cache', 'huggingface')}")
        print("\nTo deploy to air-gapped system:")
        print("1. Copy the entire cache directory to the target system")
        print("2. Set TRANSFORMERS_CACHE environment variable to the copied cache path")
        print("3. Ensure TRANSFORMERS_OFFLINE=1 is set in .env")
        
    except Exception as e:
        print(f"Error downloading model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_model()
