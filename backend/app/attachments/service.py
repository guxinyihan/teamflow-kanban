"""Only generated keys touch the private store; names are display metadata."""
import logging
from pathlib import Path
import re
import time
import uuid

from fastapi import HTTPException

from ..config import settings

logger = logging.getLogger(__name__)
CONTENT_TYPES = {".txt": "text/plain", ".pdf": "application/pdf", ".png": "image/png",
                 ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def safe_filename(name):
    if not name or len(name) > 200 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise HTTPException(400, detail="Filename is not safe")
    if name != name.strip() or name.endswith(".") or name in (".", ".."):
        raise HTTPException(400, detail="Filename is not safe")
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise HTTPException(400, detail="Filename is reserved")
    return name


def validate_content(name, content, reported_type=None):
    safe_filename(name)
    expected = CONTENT_TYPES.get(Path(name).suffix.lower())
    if expected is None:
        raise HTTPException(415, detail="Allowed files: PDF, UTF-8 text, PNG and JPEG")
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail="File exceeds the upload size limit")
    if not content:
        raise HTTPException(400, detail="File is empty")
    reported_type = reported_type.split(";", 1)[0].strip().lower() if reported_type else None
    if reported_type and reported_type not in (expected, "application/octet-stream"):
        raise HTTPException(415, detail="File MIME type does not match its extension")
    valid = True
    if expected == "application/pdf":
        valid = content.startswith(b"%PDF-") and b"%%EOF" in content[-2048:]
    elif expected == "image/png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n") and content[12:16] == b"IHDR" and b"IEND" in content[-32:]
    elif expected == "image/jpeg":
        valid = content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
    else:
        try:
            text = content.decode("utf-8")
            valid = not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|<\s*(script|html|svg)|<!doctype\s+html|javascript:", text, re.IGNORECASE)
        except UnicodeDecodeError:
            valid = False
    if not valid:
        raise HTTPException(415, detail="File contents do not match the allowed format")
    return expected


def storage_root():
    root = Path(settings.UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def private_path(storage_name):
    if not storage_name or not KEY_PATTERN.fullmatch(storage_name):
        raise HTTPException(404, detail="Attachment bytes are unavailable")
    root = storage_root()
    path = (root / storage_name).resolve()
    if path.parent != root:
        raise HTTPException(404, detail="Attachment bytes are unavailable")
    return path


def store_content(name, content, reported_type=None):
    content_type = validate_content(name, content, reported_type)
    key = uuid.uuid4().hex
    path = private_path(key)
    created = False
    try:
        with path.open("xb") as target:
            created = True
            target.write(content)
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise HTTPException(500, detail="Unable to store attachment")
    return {"storage_name": key, "original_name": name, "content_type": content_type, "size": len(content)}


async def store_upload(upload):
    # Multipart parsers may reduce legacy Windows paths to a basename. Validate
    # the supplied header as well so traversal/path input is rejected explicitly.
    disposition = upload.headers.get("content-disposition", "")
    supplied = re.search(r'(?:^|;)\s*filename\s*=\s*(?:"([^\"]*)"|([^;]*))', disposition, re.IGNORECASE)
    if supplied:
        safe_filename(supplied.group(1) if supplied.group(1) is not None else supplied.group(2).strip())
    safe_filename(upload.filename)
    content = bytearray()
    while chunk := await upload.read(64 * 1024):
        content.extend(chunk)
        if len(content) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail="File exceeds the upload size limit")
    return store_content(upload.filename, bytes(content), upload.content_type)


def cleanup_files(attachments):
    """DB deletion commits first; failed unlinks leave private orphan bytes."""
    for attachment in attachments:
        key = attachment if isinstance(attachment, str) else attachment.storage_name
        if not key:
            continue
        try:
            private_path(key).unlink(missing_ok=True)
        except (OSError, HTTPException):
            logger.warning("Private attachment cleanup deferred")


def cleanup_orphan_files(db, minimum_age_seconds=3600):
    """A maintenance operation; age grace protects in-flight upload staging."""
    from ..models import Attachment
    referenced = {row[0] for row in db.query(Attachment.storage_name).filter(Attachment.storage_name.is_not(None)).all()}
    cutoff = time.time() - minimum_age_seconds
    removed = 0
    for path in storage_root().iterdir():
        if KEY_PATTERN.fullmatch(path.name) and path.name not in referenced and path.is_file() and path.stat().st_mtime < cutoff:
            private_path(path.name).unlink(missing_ok=True)
            removed += 1
    return removed
