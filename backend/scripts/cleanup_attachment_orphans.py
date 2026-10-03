"""Remove unreferenced private generated files after an upload staging grace."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.attachments.service import cleanup_orphan_files
from app.database import SessionLocal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum-age-seconds", type=int, default=3600)
    args = parser.parse_args()
    if args.minimum_age_seconds < 3600:
        parser.error("A grace period of at least one hour protects in-flight uploads")
    with SessionLocal() as db:
        print(f"Removed {cleanup_orphan_files(db, args.minimum_age_seconds)} private orphan files")


if __name__ == "__main__":
    main()
