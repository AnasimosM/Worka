import hashlib
import uuid
from pathlib import Path
from fastapi import UploadFile
from ..config import settings

ALLOWED = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_BYTES = 15 * 1024 * 1024

async def store_upload(file: UploadFile):
    if file.content_type not in ALLOWED:
        raise ValueError("Only JPG, PNG, WebP, and PDF evidence files are allowed.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Evidence file exceeds 15 MB.")
    digest = hashlib.sha256(data).hexdigest()
    suffix = Path(file.filename or "evidence").suffix.lower()
    name = f"{uuid.uuid4().hex}{suffix}"
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    (settings.upload_path / name).write_bytes(data)
    return name, digest, len(data)
