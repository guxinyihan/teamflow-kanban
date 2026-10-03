"""Explicit migration execution; application imports never create tables."""
from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.database import Base
from app import models  # noqa: F401 -- registers metadata for alembic check

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run(connection):
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        if connection.in_transaction():
            raise RuntimeError("SQLite migrations require a connection without an outer transaction")
        # Only this migration connection disables FK checks for batch rebuilds.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    try:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=sqlite, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        if sqlite:
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if broken:
                raise RuntimeError("Migration produced invalid foreign keys; restore the database backup")
            connection.commit()
    finally:
        if sqlite:
            if connection.in_transaction():
                connection.rollback()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


provided = config.attributes.get("connection")
if context.is_offline_mode():
    raise RuntimeError("TeamFlow data backfills require an online database connection")
elif provided is not None:
    run(provided)
else:
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
