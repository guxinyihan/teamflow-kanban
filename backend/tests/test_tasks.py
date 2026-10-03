"""Task domain regressions: authorization, atomic ordering, WIP and subresources."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest


def state(client, users, board):
    response = client.get(f"/api/boards/{board['board_id']}/state", headers=users["owner"]["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def create(client, users, board, title="Task", column=None):
    response = client.post(
        f"/api/tasks/?board_id={board['board_id']}",
        json={"title": title, "column_id": column or board["column_ids"][0]},
        headers=users["owner"]["headers"],
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def assert_order(snapshot):
    active = [task for task in snapshot["tasks"] if not task["is_archived"]]
    assert len({task["id"] for task in snapshot["tasks"]}) == len(snapshot["tasks"])
    for column in snapshot["columns"]:
        positions = sorted(task["position"] for task in active if task["column_id"] == column["id"])
        assert positions == list(range(len(positions)))


@pytest.mark.parametrize("resource,method,payload", [
    ("labels/", "post", {"name": "Secret", "color": "#123456"}),
    ("comments/", "post", {"content": "Unauthorized"}),
    ("checklist/", "post", {"content": "Unauthorized"}),
])
def test_guessed_task_id_never_grants_mutation(client, users, board, resource, method, payload):
    task = create(client, users, board)
    response = getattr(client, method)(f"/api/tasks/{task['id']}/{resource}", json=payload, headers=users["outsider"]["headers"])
    assert response.status_code == 403, response.text
    assert client.get(f"/api/tasks/{task['id']}", headers=users["outsider"]["headers"]).status_code == 403
    assert client.put(f"/api/tasks/{task['id']}", json={"title": "Overwritten"}, headers=users["outsider"]["headers"]).status_code == 403
    assert client.delete(f"/api/tasks/{task['id']}", headers=users["outsider"]["headers"]).status_code == 403
    assert state(client, users, board)["tasks"][0]["title"] == "Task"


def test_atomic_move_normalizes_source_and_target(client, users, board):
    tasks = [create(client, users, board, str(index)) for index in range(4)]
    destination = [create(client, users, board, f"Destination {index}", board["column_ids"][1]) for index in range(2)]
    headers = users["owner"]["headers"]
    source_id, destination_id = board["column_ids"][:2]
    steps = [
        (source_id, 0, [tasks[2], tasks[0], tasks[1], tasks[3]], destination),
        (source_id, 3, [tasks[0], tasks[1], tasks[3], tasks[2]], destination),
        (destination_id, 1, [tasks[0], tasks[1], tasks[3]], [destination[0], tasks[2], destination[1]]),
    ]
    expected_ids = {task["id"] for task in tasks + destination}
    for target, index, expected_source, expected_destination in steps:
        snapshot = state(client, users, board)
        response = client.post(f"/api/tasks/{tasks[2]['id']}/move", json={"target_column_id": target, "target_index": index, "expected_revision": snapshot["revision"]}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == snapshot["revision"] + 1
        after = state(client, users, board)
        assert_order(after)
        assert {task["id"] for task in after["tasks"]} == expected_ids
        for column_id, expected in ((source_id, expected_source), (destination_id, expected_destination)):
            rows = sorted((task for task in after["tasks"] if task["column_id"] == column_id), key=lambda task: task["position"])
            assert [task["id"] for task in rows] == [task["id"] for task in expected]


def test_positions_only_change_through_move(client, users, board):
    task = create(client, users, board)
    response = client.put(f"/api/tasks/{task['id']}", json={"position": 30}, headers=users["owner"]["headers"])
    assert response.status_code == 422
    assert state(client, users, board)["tasks"][0]["position"] == 0


def test_delete_archive_restore_preserve_order_and_wip(client, users, board):
    tasks = [create(client, users, board, str(index)) for index in range(3)]
    headers = users["owner"]["headers"]
    assert client.put(f"/api/tasks/{tasks[1]['id']}", json={"is_archived": True}, headers=headers).status_code == 200
    snapshot = state(client, users, board)
    assert_order(snapshot)
    assert len([task for task in snapshot["tasks"] if task["is_archived"]]) == 1
    assert client.put(f"/api/tasks/{tasks[1]['id']}", json={"is_archived": False}, headers=headers).status_code == 200
    assert_order(state(client, users, board))
    assert client.delete(f"/api/tasks/{tasks[0]['id']}", headers=headers).status_code == 200
    assert_order(state(client, users, board))


def test_final_wip_slot_race_commits_one_move(client, users, board):
    headers = users["owner"]["headers"]
    tasks = [create(client, users, board, str(index)) for index in range(2)]
    target = board["column_ids"][1]
    response = client.patch(f"/api/boards/{board['board_id']}/columns/{target}", json={"wip_limit": 1}, headers=headers)
    assert response.status_code == 200, response.text
    before = state(client, users, board)
    def move(task):
        return client.post(f"/api/tasks/{task['id']}/move", json={"target_column_id": target, "target_index": 0, "expected_revision": before["revision"]}, headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(move, tasks))
    assert sorted(response.status_code for response in responses) == [200, 409], [response.text for response in responses]
    snapshot = state(client, users, board)
    assert len([task for task in snapshot["tasks"] if task["column_id"] == target and not task["is_archived"]]) == 1
    assert snapshot["revision"] == before["revision"] + 1
    assert_order(snapshot)
    loser = next(task for task in snapshot["tasks"] if task["column_id"] != target)
    rejected = client.post(f"/api/tasks/{loser['id']}/move", json={"target_column_id": target, "target_index": 0, "expected_revision": snapshot["revision"]}, headers=headers)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "wip_limit"
    assert state(client, users, board)["revision"] == snapshot["revision"]


def test_full_wip_column_allows_reorder_move_out_and_incoming_after_slot_is_freed(client, users, board):
    headers = users["owner"]["headers"]
    source_id, target_id = board["column_ids"][:2]
    assert client.patch(f"/api/columns/{target_id}", headers=headers, json={"wip_limit": 2}).status_code == 200
    first = create(client, users, board, "First in full column", target_id)
    second = create(client, users, board, "Second in full column", target_id)
    incoming = create(client, users, board, "Incoming work", source_id)

    def move_task(task, target, index, expected_status=200):
        before = state(client, users, board)
        response = client.post(f"/api/tasks/{task['id']}/move", headers=headers,
                               json={"target_column_id": target, "target_index": index,
                                     "expected_revision": before["revision"]})
        assert response.status_code == expected_status, response.text
        after = state(client, users, board)
        assert after["revision"] == before["revision"] + (expected_status == 200)
        assert_order(after)
        assert {row["id"] for row in after["tasks"]} == {first["id"], second["id"], incoming["id"]}
        return after

    reordered = move_task(second, target_id, 0)
    assert [row["id"] for row in reordered["tasks"] if row["column_id"] == target_id] == [second["id"], first["id"]]
    rejected = move_task(incoming, target_id, 2, 409)
    assert next(column for column in rejected["columns"] if column["id"] == target_id)["active_count"] == 2
    freed = move_task(first, source_id, 1)
    assert next(column for column in freed["columns"] if column["id"] == target_id)["active_count"] == 1
    accepted = move_task(incoming, target_id, 1)
    assert [row["id"] for row in accepted["tasks"] if row["column_id"] == target_id] == [second["id"], incoming["id"]]
    assert [row["id"] for row in accepted["tasks"] if row["column_id"] == source_id] == [first["id"]]


def test_assignment_rejects_unrelated_user(client, users, board):
    task = create(client, users, board)
    response = client.put(f"/api/tasks/{task['id']}", json={"assignee_id": users["outsider"]["user"]["id"]}, headers=users["owner"]["headers"])
    assert response.status_code in (403, 422), response.text
    assert state(client, users, board)["tasks"][0]["assigned_to"] == []


def test_labels_comments_checklists_survive_and_are_scoped(client, users, board):
    task = create(client, users, board)
    headers = users["owner"]["headers"]
    label = client.post(f"/api/tasks/{task['id']}/labels/", json={"name": "Urgent", "color": "#ff0000"}, headers=headers)
    assert label.status_code in (200, 201), label.text
    again = client.post(f"/api/tasks/{task['id']}/labels/", json={"name": "Urgent", "color": "#ff0000"}, headers=headers)
    assert again.status_code in (200, 201)
    assert len(client.get(f"/api/tasks/{task['id']}/labels/", headers=headers).json()) == 1
    comment = client.post(f"/api/tasks/{task['id']}/comments/", json={"content": "Needs review"}, headers=headers)
    assert comment.status_code in (200, 201), comment.text
    checklist = client.post(f"/api/tasks/{task['id']}/checklist/", json={"content": "Write regression"}, headers=headers)
    assert checklist.status_code == 200, checklist.text
    item_id = checklist.json()["checklist"][0]["id"]
    toggled = client.put(f"/api/tasks/{task['id']}/checklist/{item_id}/toggle/", headers=headers)
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["checklist"][0]["id"] == item_id
    assert toggled.json()["checklist"][0]["is_completed"] is True
    assert client.delete(f"/api/tasks/{task['id']}/comments/{comment.json()['id']}", headers=users["outsider"]["headers"]).status_code == 403
    assert client.delete(f"/api/tasks/{task['id']}/labels/{label.json()['id']}", headers=headers).status_code == 200


def test_board_columns_reorder_and_wip_reduction_conflict(client, users, board):
    headers = users["owner"]["headers"]
    response = client.post(f"/api/boards/{board['board_id']}/columns", json={"name": "Review", "wip_limit": 2}, headers=headers)
    assert response.status_code in (200, 201), response.text
    column_id = response.json()["id"]
    create(client, users, board, "One", column_id)
    create(client, users, board, "Two", column_id)
    response = client.patch(f"/api/boards/{board['board_id']}/columns/{column_id}", json={"wip_limit": 1}, headers=headers)
    assert response.status_code == 409
    ids = [column["id"] for column in state(client, users, board)["columns"]][::-1]
    response = client.put(f"/api/boards/{board['board_id']}/columns/reorder", json={"column_ids": ids}, headers=headers)
    assert response.status_code == 200, response.text
    columns = state(client, users, board)["columns"]
    assert [column["id"] for column in columns] == ids
    assert [column["position"] for column in columns] == list(range(len(ids)))
    assert client.delete(f"/api/boards/{board['board_id']}/columns/{column_id}", headers=headers).status_code == 409


def test_noop_move_keeps_revision_and_failed_move_has_no_activity(client, users, board):
    task = create(client, users, board)
    headers = users["owner"]["headers"]
    snapshot = state(client, users, board)
    initial_activity = client.get(f"/api/boards/{board['board_id']}/activity", headers=headers).json()
    body = {"target_column_id": task["column_id"], "target_index": 0, "expected_revision": snapshot["revision"]}
    response = client.post(f"/api/tasks/{task['id']}/move", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == snapshot["revision"]
    body["target_index"] = 100
    assert client.post(f"/api/tasks/{task['id']}/move", json=body, headers=headers).status_code == 422
    assert state(client, users, board)["revision"] == snapshot["revision"]
    assert client.get(f"/api/boards/{board['board_id']}/activity", headers=headers).json() == initial_activity


def test_archive_frees_wip_and_restore_obeys_limit(client, users, board):
    headers = users["owner"]["headers"]
    column_id = board["column_ids"][0]
    assert client.patch(f"/api/columns/{column_id}", json={"wip_limit": 1}, headers=headers).status_code == 200
    task = create(client, users, board)
    assert client.put(f"/api/tasks/{task['id']}", json={"is_archived": True}, headers=headers).status_code == 200
    create(client, users, board, "Replacement")
    response = client.put(f"/api/tasks/{task['id']}", json={"is_archived": False}, headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "wip_limit"
    snapshot = state(client, users, board)
    assert next(row for row in snapshot["tasks"] if row["id"] == task["id"])["is_archived"] is True
    assert_order(snapshot)


def test_member_assignment_and_admin_comment_moderation(client, users, board):
    task = create(client, users, board)
    response = client.patch(f"/api/tasks/{task['id']}", json={"assignee_id": users["member"]["user"]["id"]}, headers=users["owner"]["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["assignee_id"] == users["member"]["user"]["id"]
    activity = client.get(f"/api/boards/{board['board_id']}/activity", headers=users["owner"]["headers"]).json()
    assigned = next(event for event in activity if event["action"] == "task_assigned")
    assert assigned["details"]["assignee_id"] == users["member"]["user"]["id"]
    assert assigned["details"]["assignee_name"] == "Member"
    comment = client.post(f"/api/tasks/{task['id']}/comments/", json={"content": "Please moderate"}, headers=users["member"]["headers"])
    assert comment.status_code == 201, comment.text
    assert client.delete(f"/api/tasks/{task['id']}/comments/{comment.json()['id']}", headers=users["admin"]["headers"]).status_code == 200


def test_move_rejects_column_from_another_board(client, users, board):
    task = create(client, users, board)
    headers = users["owner"]["headers"]
    response = client.post(f"/api/teams/{board['team_id']}/boards", json={"name": "Different Board", "team_id": board["team_id"], "visibility": "team"}, headers=headers)
    assert response.status_code == 201, response.text
    other_id = response.json()["id"]
    other_column = client.get(f"/api/boards/{other_id}/columns", headers=headers).json()[0]["id"]
    before = state(client, users, board)
    response = client.post(f"/api/tasks/{task['id']}/move", json={"target_column_id": other_column, "target_index": 0, "expected_revision": before["revision"]}, headers=headers)
    assert response.status_code == 422
    assert state(client, users, board)["revision"] == before["revision"]


def test_labels_do_not_share_rows_across_boards(client, users, board):
    headers = users["owner"]["headers"]
    first = create(client, users, board)
    response = client.post(f"/api/teams/{board['team_id']}/boards", json={"name": "Another Board", "team_id": board["team_id"], "visibility": "team"}, headers=headers)
    second_board = response.json()["id"]
    second_column = client.get(f"/api/boards/{second_board}/columns", headers=headers).json()[0]["id"]
    second = client.post(f"/api/tasks/?board_id={second_board}", json={"title": "Second", "column_id": second_column}, headers=headers).json()
    labels = [client.post(f"/api/tasks/{task['id']}/labels/", json={"name": "Review", "color": "#112233"}, headers=headers).json() for task in (first, second)]
    assert labels[0]["id"] != labels[1]["id"]
    assert labels[0]["board_id"] != labels[1]["board_id"]
    assert client.delete(f"/api/tasks/{first['id']}/labels/{labels[1]['id']}", headers=headers).status_code == 404


@pytest.mark.parametrize("use_expected_revision", [True, False])
def test_independent_database_sessions_serialize_final_wip_slot(client, users, board, session_factory, use_expected_revision):
    """Separate thread connections prove database serialization across workers."""
    from fastapi import HTTPException
    from app.models import ActivityEvent, Task, User
    from app.activity.service import record_event
    from app.authorization.policy import require_board_edit
    from app.domain import board_lock
    from app.tasks.ordering import move

    tasks = [create(client, users, board, str(index)) for index in range(2)]
    headers = users["owner"]["headers"]
    target = board["column_ids"][1]
    assert client.patch(f"/api/columns/{target}", json={"wip_limit": 1}, headers=headers).status_code == 200
    before = state(client, users, board)
    barrier = Barrier(2)
    with session_factory() as session:
        initial_count = session.query(ActivityEvent).filter_by(board_id=board["board_id"]).count()

    def worker(task_id):
        with session_factory() as session:
            actor = session.get(User, users["owner"]["user"]["id"])
            task = session.get(Task, task_id)
            require_board_edit(session, task.board_id, actor)
            barrier.wait(timeout=10)
            try:
                locked = board_lock(session, task.board_id, before["revision"] if use_expected_revision else None)
                require_board_edit(session, locked.id, actor)
                task = session.get(Task, task_id)
                move(session, locked, task, target, 0)
                record_event(session, actor, "task_moved", "task", task.id, board=locked)
                session.commit()
                return 200
            except HTTPException as error:
                session.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(worker, [task["id"] for task in tasks]))
    assert sorted(statuses) == [200, 409]
    after = state(client, users, board)
    assert after["revision"] == before["revision"] + 1
    assert sum(task["column_id"] == target and not task["is_archived"] for task in after["tasks"]) == 1
    assert_order(after)
    with session_factory() as session:
        assert session.query(ActivityEvent).filter_by(board_id=board["board_id"]).count() == initial_count + 1


def test_reorder_rejects_duplicate_column_ids_without_mutation(client, users, board):
    before = state(client, users, board)
    ids = [column["id"] for column in before["columns"]]
    response = client.post(f"/api/boards/{board['board_id']}/columns/reorder", json={"column_ids": ids + [ids[0]], "expected_revision": before["revision"]}, headers=users["owner"]["headers"])
    assert response.status_code == 422
    after = state(client, users, board)
    assert after["columns"] == before["columns"]
    assert after["revision"] == before["revision"]


@pytest.mark.parametrize("field", ["title", "priority", "is_archived"])
def test_null_required_task_field_cannot_mutate_revision(client, users, board, field):
    task = create(client, users, board)
    before = state(client, users, board)
    response = client.patch(f"/api/tasks/{task['id']}", json={field: None}, headers=users["owner"]["headers"])
    assert response.status_code == 422
    after = state(client, users, board)
    assert after["revision"] == before["revision"]
    assert after["tasks"] == before["tasks"]
