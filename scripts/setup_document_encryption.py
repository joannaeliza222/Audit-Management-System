#!/usr/bin/env python3
"""
Setup script for generating a secure document encryption key.

This script generates a cryptographically secure 256-bit key for AES-256-GCM
encryption of document content in the AMS document management system.

Usage:
    python setup_document_encryption.py

The script will:
1. Generate a secure 256-bit key
2. Display the key in hexadecimal format
3. Show the .env configuration line
4. Optionally update the .env file automatically
"""

import os
import secrets
import sys
from pathlib import Path


def generate_encryption_key():
    """Generate a cryptographically secure 256-bit encryption key."""
    return secrets.token_hex(32)  # 32 bytes = 256 bits, hex = 64 characters


def get_env_file_path():
    """Get the path to the .env file in the project root."""
    # Get the script directory and go up to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / '.env'


def read_env_file(env_path):
    """Read and return the contents of the .env file."""
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def write_env_file(env_path, content):
    """Write content to the .env file."""
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(content)


def update_env_file(env_path, key_value):
    """Update the .env file with the new encryption key."""
    content = read_env_file(env_path)
    
    # Remove existing DOCUMENT_ENCRYPTION_KEY line if present
    lines = content.split('\n')
    filtered_lines = [line for line in lines if not line.startswith('DOCUMENT_ENCRYPTION_KEY=')]
    
    # Add the new key
    filtered_lines.append(f'DOCUMENT_ENCRYPTION_KEY={key_value}')
    
    # Write back to file
    new_content = '\n'.join(filtered_lines) + '\n'
    write_env_file(env_path, new_content)
    
    return True


def main():
    """Main function to generate and setup the encryption key."""
    print("=== AMS Document Encryption Key Generator ===\n")
    
    # Generate the key
    encryption_key = generate_encryption_key()
    
    print(f"Generated 256-bit encryption key:")
    print(f"Key: {encryption_key}")
    print(f"Length: {len(encryption_key)} characters (64 hex chars = 256 bits)\n")
    
    # Show the .env configuration
    print("Add this to your .env file:")
    print(f"DOCUMENT_ENCRYPTION_KEY={encryption_key}\n")
    
    # Check if .env file exists and offer to update it
    env_path = get_env_file_path()
    
    if env_path.exists():
        print(f"Found .env file at: {env_path}")
        
        # Check if key already exists
        current_content = read_env_file(env_path)
        if 'DOCUMENT_ENCRYPTION_KEY=' in current_content:
            print("WARNING: DOCUMENT_ENCRYPTION_KEY already exists in .env file!")
            print("Updating will overwrite the existing key.")
            
            # Ask for confirmation
            response = input("Do you want to update the existing key? (y/N): ").strip().lower()
            if response != 'y':
                print("Operation cancelled. Key not updated.")
                return
        
        # Ask to update automatically
        response = input("Do you want to automatically update the .env file? (Y/n): ").strip().lower()
        if response != 'n':
            try:
                update_env_file(env_path, encryption_key)
                print(f"Successfully updated .env file at: {env_path}")
                print("The encryption key has been saved.")
            except Exception as e:
                print(f"Error updating .env file: {e}")
                print("Please add the key manually.")
        else:
            print("Skipping automatic update. Please add the key manually.")
    else:
        print(f"No .env file found at: {env_path}")
        print("Please create a .env file and add the key manually.")
    
    print("\n=== Security Notes ===")
    print("1. Keep this encryption key secure and never commit it to version control")
    print("2. If you lose this key, all encrypted documents will be permanently unreadable")
    print("3. Back up this key in a secure location")
    print("4. Rotate this key regularly (requires re-encrypting all documents)")
    
    print("\n=== Next Steps ===")
    print("1. Restart your Flask application to load the new key")
    print("2. Test document upload and retrieval functionality")
    print("3. Verify that documents can be properly encrypted and decrypted")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)