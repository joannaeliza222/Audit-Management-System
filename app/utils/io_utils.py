"""
IO utilities
- Secure file saving
- Path helpers
- Streaming helpers for downloads
"""

import os
from werkzeug.utils import secure_filename


def save_uploaded_file(file_storage, upload_folder: str, prefix: str = "") -> tuple[str, str]:
    os.makedirs(upload_folder, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    stored = f"{prefix}{filename}" if prefix else filename
    path = os.path.join(upload_folder, stored)
    file_storage.save(path)
    return stored, path
