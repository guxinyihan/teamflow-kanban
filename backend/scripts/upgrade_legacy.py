"""Preflight and adopt an upstream ORM-created database without deleting data.

SQLite: python scripts/upgrade_legacy.py --database-url sqlite:///old.db --apply
PostgreSQL: take a pg_dump backup, then use --apply --backup-confirmed.
The default invocation only validates the schema and reports the intended steps.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import os
import sqlite3
import sys

from alembic import command
from alembic.config import Config
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
BASELINE = "0001_upstream"
LEGACY_HEAD = "0f9401067cde"
EXPECTED = {
    "users": "id email username hashed_password full_name created_at",
    "teams": "id name description created_at created_by_id",
    "team_members": "team_id user_id role joined_at",
    "boards": "id name description created_at created_by_id team_id is_public",
    "board_members": "board_id user_id role joined_at",
    "tasks": "id title description status priority position due_date created_at updated_at creator_id board_id is_archived checklist",
    "labels": "id name color",
    "task_labels": "task_id label_id",
    "task_members": "task_id user_id",
    "comments": "id content created_at updated_at task_id user_id",
    "attachments": "id filename file_path url created_at task_id user_id",
}
FOREIGN_KEYS = {
    "users": set(), "labels": set(),
    "teams": {("created_by_id", "users", "id")},
    "team_members": {("team_id", "teams", "id"), ("user_id", "users", "id")},
    "boards": {("created_by_id", "users", "id"), ("team_id", "teams", "id")},
    "board_members": {("board_id", "boards", "id"), ("user_id", "users", "id")},
    "tasks": {("creator_id", "users", "id"), ("board_id", "boards", "id")},
    "task_labels": {("task_id", "tasks", "id"), ("label_id", "labels", "id")},
    "task_members": {("task_id", "tasks", "id"), ("user_id", "users", "id")},
    "comments": {("task_id", "tasks", "id"), ("user_id", "users", "id")},
    "attachments": {("task_id", "tasks", "id"), ("user_id", "users", "id")},
}


def preflight(connection):
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    if tables - {"alembic_version"} != set(EXPECTED):
        raise RuntimeError("Database is not the complete upstream schema; no changes were made")
    for table, expected in EXPECTED.items():
        actual = {column["name"] for column in inspector.get_columns(table)}
        if actual != set(expected.split()):
            raise RuntimeError(f"Unexpected columns in {table}; no changes were made")
        primary_key = set(inspector.get_pk_constraint(table)["constrained_columns"])
        expected_primary = ({"team_id", "user_id"} if table == "team_members" else
                            {"board_id", "user_id"} if table == "board_members" else
                            set() if table in ("task_labels", "task_members") else {"id"})
        if primary_key != expected_primary:
            raise RuntimeError(f"Unexpected primary key in {table}; no changes were made")
        foreign_keys = set()
        for foreign_key in inspector.get_foreign_keys(table):
            if len(foreign_key["constrained_columns"]) != 1 or len(foreign_key["referred_columns"]) != 1:
                raise RuntimeError(f"Unexpected foreign key in {table}; no changes were made")
            foreign_keys.add((foreign_key["constrained_columns"][0], foreign_key["referred_table"],
                              foreign_key["referred_columns"][0]))
        if foreign_keys != FOREIGN_KEYS[table]:
            raise RuntimeError(f"Unexpected foreign keys in {table}; no changes were made")
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        for name, column in columns.items():
            affinity = column["type"]._type_affinity
            expected_type = (sa.Integer if name == "id" or name.endswith("_id") or name == "position"
                             else sa.DateTime if name.endswith("_at") or name == "due_date"
                             else sa.Boolean if name in ("is_public", "is_archived")
                             else sa.JSON if name == "checklist" else sa.String)
            if affinity is not expected_type:
                raise RuntimeError(f"Unexpected type for {table}.{name}; no changes were made")
    if "alembic_version" in tables:
        versions = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
        if versions not in ([], [LEGACY_HEAD], [BASELINE]):
            raise RuntimeError("Unrecognized upstream Alembic revision; no changes were made")
    if connection.dialect.name == "sqlite":
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise RuntimeError("Legacy database contains invalid foreign keys; repair before upgrade")
    for field in ("username", "email"):
        duplicate = connection.execute(sa.text(
            f"SELECT lower({field}) FROM users WHERE {field} IS NOT NULL GROUP BY lower({field}) HAVING count(*) > 1"
        )).first()
        if duplicate:
            raise RuntimeError(f"Legacy users have duplicate case-insensitive {field}; resolve accounts before upgrade")
    # Validate nullable upstream references that FK checks alone cannot catch.
    for query in (
        "SELECT t.id FROM teams t LEFT JOIN users u ON t.created_by_id=u.id WHERE u.id IS NULL",
        "SELECT b.id FROM boards b LEFT JOIN teams t ON b.team_id=t.id LEFT JOIN users u ON b.created_by_id=u.id WHERE t.id IS NULL OR u.id IS NULL",
        "SELECT t.id FROM tasks t LEFT JOIN boards b ON t.board_id=b.id LEFT JOIN users u ON t.creator_id=u.id WHERE b.id IS NULL OR u.id IS NULL",
    ):
        if connection.execute(sa.text(query)).first():
            raise RuntimeError("Legacy data has missing ownership references; repair before upgrade")
    return {"tables": len(EXPECTED), "baseline": BASELINE, "target": "0002_teamflow"}


def upgrade_legacy(connection):
    preflight(connection)
    connection.commit()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.attributes["connection"] = connection
    # Only the recognized migration marker is replaced; application rows remain.
    command.stamp(config, BASELINE, purge=True)
    command.upgrade(config, "head")


def backup_sqlite(url):
    path = Path(sa.engine.make_url(url).database or "")
    if not path.is_file():
        raise RuntimeError("Legacy SQLite database file does not exist")
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(path.name + f".before-teamflow-{suffix}.bak")
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-confirmed", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Supply --database-url or DATABASE_URL explicitly")
    engine = sa.create_engine(args.database_url)
    try:
        with engine.connect() as connection:
            result = preflight(connection)
            connection.commit()
            if not args.apply:
                print(f"Validated {result['tables']} upstream tables. Use --apply to back up and migrate.")
                return
            if engine.dialect.name == "sqlite":
                backup = backup_sqlite(args.database_url)
                print(f"SQLite backup created: {backup.name}")
            elif not args.backup_confirmed:
                parser.error("Take a PostgreSQL pg_dump backup first, then pass --backup-confirmed")
            upgrade_legacy(connection)
            print("Data-preserving TeamFlow migration completed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
