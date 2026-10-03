"""Copy approved legacy uploads into private storage without removing originals.

Run after database migration with an explicit --source-dir. Unsupported/missing
records remain metadata-only and their protected downloads return 404.
"""
import argparse
import json
from pathlib import Path, PureWindowsPath
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException
from app.attachments.service import cleanup_files, store_content
from app.config import settings
from app.database import SessionLocal
from app.models import Attachment


def approved_source(source_root, stored_path):
    root = Path(source_root).resolve(strict=True)
    if not root.is_dir() or not stored_path:
        raise ValueError("Legacy source directory/path is invalid")
    supplied = Path(stored_path)
    # Windows-looking absolute paths are not relative names on POSIX either.
    windows = PureWindowsPath(stored_path)
    if ".." in supplied.parts or ".." in windows.parts:
        raise ValueError("Legacy path escapes source directory")
    if supplied.is_absolute():
        candidate = supplied.resolve()
    elif windows.drive:
        raise ValueError("Legacy path is not in the approved source directory")
    else:
        parts = supplied.parts
        if len(parts) == 2 and parts[0] == root.name:
            parts = parts[1:]
        candidate = root.joinpath(*parts).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("Legacy path escapes source directory")
    return candidate


def import_legacy_attachments(db, source_dir):
    report = {"imported": 0, "missing": 0, "unsupported": 0, "unsafe": 0}
    staged = []
    try:
        for attachment in db.query(Attachment).filter(Attachment.storage_name.is_(None)).all():
            try:
                source = approved_source(source_dir, attachment.file_path)
            except (ValueError, OSError):
                report["unsafe"] += 1
                continue
            if not source.is_file():
                report["missing"] += 1
                continue
            try:
                with source.open("rb") as stream:
                    content = stream.read(settings.MAX_UPLOAD_BYTES + 1)
                original = attachment.original_name or attachment.filename or source.name
                metadata = store_content(original, content)
            except HTTPException:
                report["unsupported"] += 1
                continue
            except OSError:
                report["missing"] += 1
                continue
            staged.append(metadata["storage_name"])
            for key, value in metadata.items():
                setattr(attachment, key, value)
            attachment.filename = metadata["original_name"]
            attachment.file_path = ""
            attachment.url = f"/api/attachments/{attachment.id}/download"
            report["imported"] += 1
        db.commit()
    except Exception:
        db.rollback()
        cleanup_files(staged)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="Explicit approved legacy uploads directory")
    args = parser.parse_args()
    # Resolve before inspecting any metadata; fail fast on an invalid source.
    source_dir = args.source_dir.resolve(strict=True)
    if not source_dir.is_dir():
        parser.error("source-dir must be a directory")
    with SessionLocal() as db:
        print(json.dumps(import_legacy_attachments(db, source_dir)))


if __name__ == "__main__":
    main()
