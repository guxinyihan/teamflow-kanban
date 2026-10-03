"""Run frozen migrations on fresh and populated upstream schemas on both engines."""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import pytest
import sqlalchemy as sa

from conftest import migration_config
from scripts.upgrade_legacy import preflight, upgrade_legacy


def reflected(connection, name):
    return sa.Table(name, sa.MetaData(), autoload_with=connection)


def seed_upstream(connection):
    def insert(table_name, **values):
        table = reflected(connection, table_name)
        result = connection.execute(sa.insert(table).values(**values))
        return result.inserted_primary_key[0] if table.primary_key.columns else None

    insert("users", email="owner@example.test", username="owner", hashed_password="legacy-hash", full_name="Owner")
    insert("users", email="member@example.test", username="member", hashed_password="legacy-hash", full_name="Member")
    insert("teams", name="Legacy Team", description="Preserve this", created_by_id=1)
    insert("team_members", team_id=1, user_id=1, role="admin")
    insert("team_members", team_id=1, user_id=2, role="member")
    insert("boards", name="Private board", team_id=1, created_by_id=1, is_public=False)
    insert("boards", name="Shared board", team_id=1, created_by_id=1, is_public=True)
    insert("board_members", board_id=1, user_id=1, role="admin")
    insert("board_members", board_id=1, user_id=2, role="member")
    checklist = [{"id": 1, "content": "Keep checklist", "is_completed": True}]
    for title, board_id, status, position, archived in (
        ("Legacy task A", 1, "in_progress", 7, False),
        ("Legacy task B", 1, "in_progress", 7, False),
        ("Legacy task C", 2, "todo", None, False),
        ("Archived task", 1, "done", -4, True),
    ):
        insert("tasks", title=title, description="Keep description", board_id=board_id,
               creator_id=1, status=status, priority="high", position=position,
               is_archived=archived, checklist=checklist)
    insert("labels", name="Shared Legacy Label", color="#123456")
    insert("labels", name="Unused Legacy Label", color="#654321")
    insert("task_labels", task_id=1, label_id=1)
    insert("task_labels", task_id=3, label_id=1)
    insert("task_members", task_id=1, user_id=2)
    insert("comments", content="Keep the discussion", task_id=1, user_id=2)
    insert("attachments", filename="report.pdf", file_path="uploads/legacy-report.pdf",
           url="/uploads/legacy-report.pdf", task_id=1, user_id=2)
    connection.commit()


def test_fresh_migration_matches_application_metadata(database_engine):
    from app.database import Base
    from app import models  # noqa: F401

    with database_engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "0002_teamflow"
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert differences == [], differences
        if connection.dialect.name == "sqlite":
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()


@pytest.mark.parametrize("legacy_marker", [None, "0f9401067cde"])
def test_populated_upstream_upgrade_preserves_data(unmigrated_engine, legacy_marker):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "0001_upstream")
        seed_upstream(connection)
        if legacy_marker:
            connection.execute(sa.text("UPDATE alembic_version SET version_num=:version"), {"version": legacy_marker})
        else:
            connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.commit()
        assert preflight(connection)["tables"] == 11
        connection.commit()
        upgrade_legacy(connection)
        users, teams, members, boards, tasks, labels, links, attachments = (
            reflected(connection, name) for name in
            ("users", "teams", "team_members", "boards", "tasks", "labels", "task_labels", "attachments")
        )
        assert connection.execute(sa.select(sa.func.count()).select_from(users)).scalar_one() == 2
        assert connection.execute(sa.select(teams.c.owner_id)).scalar_one() == 1
        assert set(connection.execute(sa.select(members.c.user_id, members.c.role)).all()) == {(1, "owner"), (2, "member")}
        assert connection.execute(sa.select(sa.func.count()).select_from(reflected(connection, "board_members"))).scalar_one() == 2
        assert connection.execute(sa.select(sa.func.count()).select_from(reflected(connection, "task_members"))).scalar_one() == 1
        visibility = dict(connection.execute(sa.select(boards.c.id, boards.c.visibility)).all())
        assert visibility == {1: "private", 2: "team"}
        rows = connection.execute(sa.select(tasks).order_by(tasks.c.id)).mappings().all()
        assert [row["title"] for row in rows] == ["Legacy task A", "Legacy task B", "Legacy task C", "Archived task"]
        assert [row["position"] for row in rows[:2]] == [0, 1]
        assert rows[0]["assignee_id"] == 2
        assert rows[3]["is_archived"] and rows[3]["archived_at"] is not None
        assert all(row["checklist"][0]["content"] == "Keep checklist" for row in rows)
        assert connection.execute(sa.text("SELECT content FROM comments")).scalar_one() == "Keep the discussion"
        shared_labels = connection.execute(sa.select(labels).where(labels.c.name == "Shared Legacy Label")).mappings().all()
        assert {row["board_id"] for row in shared_labels} == {1, 2}
        assert all(row["color"] == "#123456" for row in shared_labels)
        assert connection.execute(sa.select(sa.func.count()).select_from(links)).scalar_one() == 2
        assert connection.execute(sa.select(labels.c.name).where(labels.c.name == "Unused Legacy Label")).scalar_one() == "Unused Legacy Label"
        attachment = connection.execute(sa.select(attachments)).mappings().one()
        assert attachment["filename"] == "report.pdf"
        assert attachment["file_path"] == "uploads/legacy-report.pdf"
        assert attachment["original_name"] == "report.pdf"
        assert attachment["url"] == "/api/tasks/1/attachments/1/download"
        assert attachment["storage_name"] is None


def test_legacy_preflight_rejects_unknown_schema_without_changes(unmigrated_engine):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "0001_upstream")
        connection.exec_driver_sql("CREATE TABLE unrelated_data (id INTEGER)")
        connection.commit()
        with pytest.raises(RuntimeError, match="not the complete upstream schema"):
            upgrade_legacy(connection)
        connection.rollback()
        assert "unrelated_data" in sa.inspect(connection).get_table_names()
        assert "owner_id" not in {column["name"] for column in sa.inspect(connection).get_columns("teams")}


def test_invalid_legacy_owner_rejected_before_schema_mutation(unmigrated_engine):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "0001_upstream")
        connection.execute(sa.insert(reflected(connection, "teams")).values(name="Owner missing", created_by_id=None))
        connection.commit()
        with pytest.raises(RuntimeError, match="missing ownership"):
            upgrade_legacy(connection)
        connection.rollback()
        assert "owner_id" not in {column["name"] for column in sa.inspect(connection).get_columns("teams")}


@pytest.mark.parametrize("field", ["username", "email"])
def test_case_ambiguous_legacy_accounts_rejected_without_mutation(unmigrated_engine, field):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "0001_upstream")
        users = reflected(connection, "users")
        values = [{"username": "FirstUser", "email": "first@example.test"},
                  {"username": "SecondUser", "email": "second@example.test"}]
        values[0][field] = "CaseUser" if field == "username" else "CaseUser@example.test"
        values[1][field] = values[0][field].lower()
        connection.execute(sa.insert(users), values)
        connection.commit()
        with pytest.raises(RuntimeError, match="duplicate case-insensitive"):
            upgrade_legacy(connection)
        connection.rollback()
        assert "owner_id" not in {column["name"] for column in sa.inspect(connection).get_columns("teams")}
        assert connection.execute(sa.select(sa.func.count()).select_from(users)).scalar_one() == 2


@pytest.mark.parametrize("field", ["username", "email"])
def test_database_enforces_case_insensitive_user_identifier_uniqueness(database_engine, field):
    with database_engine.begin() as connection:
        users = reflected(connection, "users")
        values = [{"username": "FirstUser", "email": "first@example.test"},
                  {"username": "SecondUser", "email": "second@example.test"}]
        values[0][field] = "CaseUser" if field == "username" else "CaseUser@example.test"
        values[1][field] = values[0][field].lower()
        connection.execute(sa.insert(users).values(**values[0]))
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(sa.insert(users).values(**values[1]))


def test_legacy_assignment_selection_respects_private_board_policy_and_preserves_old_links(unmigrated_engine):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "0001_upstream")
        seed_upstream(connection)
        users = reflected(connection, "users")
        members = reflected(connection, "team_members")
        board_members = reflected(connection, "board_members")
        assignments = reflected(connection, "task_members")
        connection.execute(sa.delete(board_members).where(board_members.c.board_id == 1, board_members.c.user_id == 2))
        for user_id, role in ((3, "admin"), (4, "member"), (5, None)):
            connection.execute(sa.insert(users).values(
                id=user_id, username=f"legacy{user_id}", email=f"legacy{user_id}@example.test", hashed_password="legacy-hash"))
            if role:
                connection.execute(sa.insert(members).values(team_id=1, user_id=user_id, role=role))
        connection.execute(sa.insert(board_members).values(board_id=1, user_id=4, role="member"))
        # User 2 lacks private-board access, user 3 is an inherited admin, user
        # 4 is explicit, and user 5 is outside the team. Only eligible users may
        # become the new single assignee; historical multi-assignee links stay.
        for task_id, user_id in ((1, 3), (1, 4), (1, 5), (2, 2), (3, 2), (4, 2)):
            connection.execute(sa.insert(assignments).values(task_id=task_id, user_id=user_id))
        old_links = set(connection.execute(sa.select(assignments.c.task_id, assignments.c.user_id)).all())
        connection.commit()
        upgrade_legacy(connection)
        tasks = reflected(connection, "tasks")
        new_assignments = dict(connection.execute(sa.select(tasks.c.id, tasks.c.assignee_id)).all())
        assert new_assignments == {1: 3, 2: None, 3: 2, 4: None}
        retained = reflected(connection, "task_members")
        assert set(connection.execute(sa.select(retained.c.task_id, retained.c.user_id)).all()) == old_links


def test_legacy_duplicate_labels_survive_when_a_disambiguation_name_already_exists(unmigrated_engine):
    with unmigrated_engine.connect() as connection:
        command.upgrade(migration_config(connection), "0001_upstream")
        seed_upstream(connection)
        labels = reflected(connection, "labels")
        links = reflected(connection, "task_labels")
        connection.execute(sa.update(labels).where(labels.c.id == 1).values(name="A"))
        connection.execute(sa.update(labels).where(labels.c.id == 2).values(name="A [legacy 3]"))
        duplicate_id = connection.execute(sa.insert(labels).values(name="A", color="#abcdef").returning(labels.c.id)).scalar_one()
        assert duplicate_id == 3
        connection.execute(sa.insert(links), [{"task_id": 1, "label_id": 2}, {"task_id": 1, "label_id": 3}])
        connection.commit()
        upgrade_legacy(connection)
        labels, links = reflected(connection, "labels"), reflected(connection, "task_labels")
        rows = connection.execute(sa.select(labels).where(labels.c.board_id == 1)).mappings().all()
        assert {row["id"] for row in rows} == {1, 2, 3}
        assert len({row["normalized_name"] for row in rows}) == 3
        assert all(row["name"].startswith("A") for row in rows)
        assert connection.execute(sa.select(labels.c.color).where(labels.c.id == 3)).scalar_one() == "#abcdef"
        retained = set(connection.execute(sa.select(links.c.task_id, links.c.label_id).where(links.c.task_id == 1)).all())
        assert retained == {(1, 1), (1, 2), (1, 3)}
        assert connection.execute(sa.select(sa.func.count()).select_from(links)).scalar_one() == 4
