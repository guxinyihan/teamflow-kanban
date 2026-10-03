"""Disposable SQLite/PostgreSQL fixtures using the production Alembic chain."""

from pathlib import Path
import os
import secrets
import sys
import uuid

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
os.environ.setdefault("ENVIRONMENT", "test")


def migration_config(connection=None):
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@pytest.fixture
def unmigrated_engine(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    schema = None
    admin_engine = None
    if url:
        # Every test gets a private PostgreSQL schema. Never drop a shared database.
        admin_engine = sa.create_engine(url)
        schema = "test_" + uuid.uuid4().hex
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        engine = sa.create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = sa.create_engine(
            f"sqlite:///{(tmp_path / 'teamflow.sqlite').as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @sa.event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    try:
        yield engine
    finally:
        engine.dispose()
        if admin_engine is not None:
            with admin_engine.begin() as connection:
                connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin_engine.dispose()


@pytest.fixture
def database_engine(unmigrated_engine):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "head")
    return unmigrated_engine


@pytest.fixture
def session_factory(database_engine, monkeypatch):
    from app import database

    factory = sessionmaker(bind=database_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(database, "engine", database_engine)
    return factory


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory, tmp_path, monkeypatch):
    from app.database import get_db
    from app.main import app
    from app.config import settings

    def isolated_db():
        with session_factory() as session:
            yield session

    # Upload roots are temporary and independent of upstream/runtime files.
    for attribute in ("ATTACHMENT_DIR", "ATTACHMENT_STORAGE_DIR", "UPLOAD_DIR"):
        if hasattr(settings, attribute):
            monkeypatch.setattr(settings, attribute, tmp_path / "attachments")
    app.dependency_overrides[get_db] = isolated_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def users(client):
    result = {}
    password = "Test-only strong password 42!"
    for name in ("owner", "admin", "member", "outsider"):
        response = client.post("/api/auth/register", json={
            "email": f"{name}@example.test", "username": name,
            "full_name": name.title(), "password": password,
        })
        assert response.status_code in (200, 201), response.text
        user = response.json()
        login = client.post("/api/auth/login", data={"username": name, "password": password})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        result[name] = {"user": user, "token": token, "headers": {"Authorization": f"Bearer {token}"}}
    return result


@pytest.fixture
def board(client, users, db):
    from app.models import TeamMember

    headers = users["owner"]["headers"]
    response = client.post("/api/teams/", headers=headers, json={
        "name": "CS Project Team", "description": "Authorization regression fixtures",
    })
    assert response.status_code in (200, 201), response.text
    team_id = response.json()["id"]
    for role in ("admin", "member"):
        db.add(TeamMember(team_id=team_id, user_id=users[role]["user"]["id"], role=role))
    db.commit()
    response = client.post(f"/api/teams/{team_id}/boards", headers=headers, json={
        "name": "Software Engineering Project", "team_id": team_id,
        "visibility": "team",
    })
    assert response.status_code in (200, 201), response.text
    board_id = response.json()["id"]
    response = client.get(f"/api/boards/{board_id}/columns", headers=headers)
    assert response.status_code == 200, response.text
    columns = response.json()
    return {"board_id": board_id, "team_id": team_id,
            "column_ids": [column["id"] for column in columns], "columns": columns}
