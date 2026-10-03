"""Role matrix, owner invariant and membership revocation regression tests."""
import pytest


@pytest.mark.parametrize("actor", ["owner", "admin", "member"])
def test_team_members_can_read_team_board(client, users, board, actor):
    response = client.get(f"/api/boards/{board['board_id']}/state", headers=users[actor]["headers"])
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("actor", ["member", "outsider"])
def test_only_managers_create_boards(client, users, board, actor):
    response = client.post(f"/api/teams/{board['team_id']}/boards", headers=users[actor]["headers"],
                           json={"name": "Unauthorized", "visibility": "team"})
    assert response.status_code in (403, 404)


@pytest.mark.parametrize("actor", ["owner", "admin"])
def test_managers_can_create_board(client, users, board, actor):
    response = client.post(f"/api/teams/{board['team_id']}/boards", headers=users[actor]["headers"],
                           json={"name": "Allowed", "visibility": "team"})
    assert response.status_code == 201, response.text


def test_private_board_requires_explicit_member(client, users, board):
    response = client.patch(f"/api/boards/{board['board_id']}", headers=users["owner"]["headers"],
                            json={"visibility": "private"})
    assert response.status_code == 200, response.text
    state = f"/api/boards/{board['board_id']}/state"
    assert client.get(state, headers=users["member"]["headers"]).status_code == 403
    assert client.get(state, headers=users["admin"]["headers"]).status_code == 200
    response = client.post(f"/api/teams/{board['team_id']}/boards/{board['board_id']}/members",
                           headers=users["owner"]["headers"],
                           json={"user_id": users["member"]["user"]["id"], "role": "member"})
    assert response.status_code == 201, response.text
    assert client.get(state, headers=users["member"]["headers"]).status_code == 200


def test_owner_cannot_be_removed_or_demoted(client, users, board, db):
    owner_id = users["owner"]["user"]["id"]
    url = f"/api/teams/{board['team_id']}/members/{owner_id}"
    assert client.delete(url, headers=users["owner"]["headers"]).status_code == 409
    assert client.patch(url, headers=users["owner"]["headers"], json={"role": "member"}).status_code == 409
    from app.models import Team, TeamMember
    db.expire_all()
    assert db.get(Team, board["team_id"]).owner_id == owner_id
    assert db.get(TeamMember, (board["team_id"], owner_id)).role == "owner"


def test_owner_transfer_is_atomic_and_requires_existing_member(client, users, board, db):
    url = f"/api/teams/{board['team_id']}/transfer-ownership"
    owner_id, member_id = users["owner"]["user"]["id"], users["member"]["user"]["id"]
    denied = client.post(url, headers=users["owner"]["headers"], json={"user_id": users["outsider"]["user"]["id"]})
    assert denied.status_code == 400
    response = client.post(url, headers=users["owner"]["headers"], json={"user_id": member_id})
    assert response.status_code == 200, response.text
    from app.models import Team, TeamMember
    db.expire_all()
    assert db.get(Team, board["team_id"]).owner_id == member_id
    assert db.get(TeamMember, (board["team_id"], member_id)).role == "owner"
    assert db.get(TeamMember, (board["team_id"], owner_id)).role == "admin"
    assert client.post(url, headers=users["owner"]["headers"], json={"user_id": owner_id}).status_code == 403


def test_admin_cannot_manage_admin_roles(client, users, board):
    url = f"/api/teams/{board['team_id']}/members/{users['member']['user']['id']}"
    assert client.patch(url, headers=users["admin"]["headers"], json={"role": "admin"}).status_code == 403
    assert client.patch(url, headers=users["owner"]["headers"], json={"role": "admin"}).status_code == 200
    assert client.delete(url, headers=users["admin"]["headers"]).status_code == 403


def test_removed_member_loses_board_access_and_assignment(client, users, board, db):
    response = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=users["owner"]["headers"],
                           json={"title": "Assigned work", "column_id": board["column_ids"][0],
                                 "assignee_id": users["member"]["user"]["id"]})
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    removed = client.delete(f"/api/teams/{board['team_id']}/members/{users['member']['user']['id']}",
                            headers=users["admin"]["headers"])
    assert removed.status_code == 200, removed.text
    assert client.get(f"/api/tasks/{task_id}", headers=users["member"]["headers"]).status_code == 403
    from app.models import Task
    db.expire_all()
    assert db.get(Task, task_id).assignee_id is None


def test_member_cannot_add_unrelated_board_account(client, users, board):
    response = client.post(f"/api/teams/{board['team_id']}/boards/{board['board_id']}/members",
                           headers=users["owner"]["headers"],
                           json={"user_id": users["outsider"]["user"]["id"], "role": "member"})
    assert response.status_code == 400


@pytest.mark.parametrize("visibility", ["team", "private", "public-read"])
def test_management_and_activity_role_matrix_with_explicit_read_only_cases(client, users, board, visibility):
    owner_headers = users["owner"]["headers"]
    changed = client.patch(f"/api/boards/{board['board_id']}", headers=owner_headers,
                           json={"visibility": visibility})
    assert changed.status_code == 200, changed.text
    for actor in ("owner", "admin", "member", "outsider"):
        headers = users[actor]["headers"]
        manages = actor in ("owner", "admin")
        reads = manages or (visibility == "team" and actor == "member") or visibility == "public-read"
        team_update = client.patch(f"/api/teams/{board['team_id']}", headers=headers, json={"name": "Managed Team"})
        assert team_update.status_code == (200 if manages else 403), (visibility, actor, "team-update")
        board_update = client.patch(f"/api/boards/{board['board_id']}", headers=headers, json={"name": "Managed Board"})
        assert board_update.status_code == (200 if manages else 403), (visibility, actor, "board-update")
        created = client.post(f"/api/boards/{board['board_id']}/columns", headers=headers,
                              json={"name": f"Role matrix {actor}"})
        assert created.status_code == (201 if manages else 403), (visibility, actor, "column-create")
        column_id = created.json()["id"] if manages else board["column_ids"][0]
        updated = client.patch(f"/api/columns/{column_id}", headers=headers, json={"name": "Updated", "wip_limit": 2})
        assert updated.status_code == (200 if manages else 403), (visibility, actor, "column-update-wip")
        deleted = client.delete(f"/api/columns/{column_id}", headers=headers)
        assert deleted.status_code == (200 if manages else 403), (visibility, actor, "column-delete")
        activity = client.get(f"/api/boards/{board['board_id']}/activity", headers=headers)
        assert activity.status_code == (200 if reads else 403), (visibility, actor, "activity-read")
        edits_tasks = manages or (visibility == "team" and actor == "member")
        task = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=headers,
                           json={"title": f"Matrix work {actor}", "column_id": board["column_ids"][0]})
        assert task.status_code == (201 if edits_tasks else 403), (visibility, actor, "task-create")
        if edits_tasks:
            task_id = task.json()["id"]
            patched = client.patch(f"/api/tasks/{task_id}", headers=headers, json={"title": "Authorized edit"})
            assert patched.status_code == 200, (visibility, actor, "task-update")
            assert client.delete(f"/api/tasks/{task_id}", headers=headers).status_code == 200


@pytest.mark.parametrize("actor", ["admin", "member", "outsider"])
def test_only_owner_can_delete_team(client, users, board, actor):
    response = client.delete(f"/api/teams/{board['team_id']}", headers=users[actor]["headers"])
    assert response.status_code in (403, 404)
    assert client.get(f"/api/teams/{board['team_id']}", headers=users["owner"]["headers"]).status_code == 200


@pytest.mark.parametrize("delete_team", [False, True])
def test_board_and_team_deletion_remove_related_rows_and_private_bytes(client, users, board, db, delete_team):
    import sqlalchemy as sa
    from app import models as m
    from app.attachments.service import private_path

    headers = users["owner"]["headers"]
    response = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=headers,
                           json={"title": "Delete with related resources", "column_id": board["column_ids"][0],
                                 "assignee_id": users["member"]["user"]["id"]})
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    comment = client.post(f"/api/tasks/{task_id}/comments/", headers=headers, json={"content": "Delete this child"})
    assert comment.status_code == 201, comment.text
    label = client.post(f"/api/tasks/{task_id}/labels/", headers=headers, json={"name": "Cleanup", "color": "#123456"})
    assert label.status_code in (200, 201), label.text
    upload = client.post(f"/api/tasks/{task_id}/attachments/", headers=headers,
                         files={"file": ("notes.txt", b"Delete private bytes", "text/plain")})
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["id"]
    item = db.get(m.Attachment, attachment_id)
    stored_path = private_path(item.storage_name)
    assert stored_path.is_file()
    invitation = client.post(f"/api/teams/{board['team_id']}/invitations", headers=headers,
                             json={"email": "outsider@example.test", "role": "member"})
    assert invitation.status_code == 201, invitation.text
    db.rollback()  # release read transactions before the deletion transaction
    path = (f"/api/teams/{board['team_id']}" if delete_team else
            f"/api/teams/{board['team_id']}/boards/{board['board_id']}")
    deleted = client.delete(path, headers=headers)
    assert deleted.status_code == 200, deleted.text
    db.expire_all()
    assert db.get(m.Board, board["board_id"]) is None
    assert db.get(m.Task, task_id) is None
    assert db.get(m.Comment, comment.json()["id"]) is None
    assert db.get(m.Label, label.json()["id"]) is None
    assert db.get(m.Attachment, attachment_id) is None
    assert not stored_path.exists()
    for model in (m.BoardMember, m.BoardColumn, m.ActivityEvent):
        assert db.scalar(sa.select(sa.func.count()).select_from(model).where(model.board_id == board["board_id"])) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(m.task_labels).where(m.task_labels.c.task_id == task_id)) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(m.task_members).where(m.task_members.c.task_id == task_id)) == 0
    if delete_team:
        assert db.get(m.Team, board["team_id"]) is None
        assert db.scalar(sa.select(sa.func.count()).select_from(m.TeamMember).where(m.TeamMember.team_id == board["team_id"])) == 0
        assert db.get(m.Invitation, invitation.json()["id"]) is None
    else:
        assert db.get(m.Team, board["team_id"]) is not None
        assert db.get(m.Invitation, invitation.json()["id"]) is not None


def test_concurrent_case_variant_registration_creates_one_account(client, db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import sqlalchemy as sa
    from app.models import User

    barrier = Barrier(2)

    def register(index):
        barrier.wait(timeout=10)
        response = client.post("/api/auth/register", json={
            "email": f"case{index}@example.test", "username": "CaseUser" if index == 0 else "caseuser",
            "password": "Test-only strong password 42!",
        })
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(register, (0, 1)))
    assert sorted(statuses) == [201, 409]
    assert db.scalar(sa.select(sa.func.count()).select_from(User).where(sa.func.lower(User.username) == "caseuser")) == 1


@pytest.mark.parametrize("visibility", ["private", "public-read"])
def test_visibility_change_clears_only_assignments_that_lose_edit_permission(client, users, board, db, visibility):
    import sqlalchemy as sa
    from app.models import Task, task_members

    headers = users["owner"]["headers"]
    member_id = users["member"]["user"]["id"]
    admin_id = users["admin"]["user"]["id"]
    created = []
    for name, assignee_id in (("Active member work", member_id), ("Archived member work", member_id),
                              ("Still eligible admin work", admin_id)):
        result = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=headers,
                             json={"title": name, "column_id": board["column_ids"][0], "assignee_id": assignee_id})
        assert result.status_code == 201, result.text
        created.append(result.json())
    archived = client.put(f"/api/tasks/{created[1]['id']}", headers=headers, json={"is_archived": True})
    assert archived.status_code == 200, archived.text
    created[1] = archived.json()
    before = client.get(f"/api/boards/{board['board_id']}/state", headers=headers).json()["revision"]
    db.rollback()
    changed = client.patch(f"/api/boards/{board['board_id']}", headers=headers, json={"visibility": visibility})
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == before + 1
    db.expire_all()
    for original in created[:2]:
        task = db.get(Task, original["id"])
        assert task.assignee_id is None
        assert task.version == original["version"] + 1
        assert task.assigned_to == []
        assert db.scalar(sa.select(sa.func.count()).select_from(task_members).where(task_members.c.task_id == task.id)) == 0
    preserved = db.get(Task, created[2]["id"])
    assert preserved.assignee_id == admin_id
    assert preserved.version == created[2]["version"]
    state = client.get(f"/api/boards/{board['board_id']}/state", headers=users["member"]["headers"])
    if visibility == "private":
        assert state.status_code == 403
    else:
        assert state.status_code == 200
        assert state.json()["permissions"]["can_edit"] is False


def test_admin_demotion_reconciles_assignments_across_visibility_and_explicit_membership(client, users, board, db):
    import sqlalchemy as sa
    from app.models import Task, task_members

    headers = users["owner"]["headers"]
    admin_id = users["admin"]["user"]["id"]
    scenarios = [(board["board_id"], board["column_ids"][0], "team", False)]
    for visibility, explicit in (("private", False), ("public-read", False), ("private", True)):
        created_board = client.post(f"/api/teams/{board['team_id']}/boards", headers=headers,
                                    json={"name": f"Demotion {visibility} {explicit}", "visibility": visibility})
        assert created_board.status_code == 201, created_board.text
        board_id = created_board.json()["id"]
        column_id = client.get(f"/api/boards/{board_id}/columns", headers=headers).json()[0]["id"]
        if explicit:
            member = client.post(f"/api/teams/{board['team_id']}/boards/{board_id}/members", headers=headers,
                                 json={"user_id": admin_id, "role": "member"})
            assert member.status_code == 201, member.text
        scenarios.append((board_id, column_id, visibility, explicit))
    tasks = []
    for board_id, column_id, visibility, explicit in scenarios:
        created = client.post(f"/api/tasks/?board_id={board_id}", headers=headers,
                              json={"title": "Assignment survives only while eligible", "column_id": column_id,
                                    "assignee_id": admin_id})
        assert created.status_code == 201, created.text
        tasks.append((created.json(), visibility == "team" or explicit))
    db.rollback()
    changed = client.patch(f"/api/teams/{board['team_id']}/members/{admin_id}", headers=headers, json={"role": "member"})
    assert changed.status_code == 200, changed.text
    db.expire_all()
    for original, remains_eligible in tasks:
        task = db.get(Task, original["id"])
        assert task.assignee_id == (admin_id if remains_eligible else None)
        assert task.version == original["version"] + (0 if remains_eligible else 1)
        association_count = db.scalar(sa.select(sa.func.count()).select_from(task_members).where(task_members.c.task_id == task.id))
        assert association_count == (1 if remains_eligible else 0)
