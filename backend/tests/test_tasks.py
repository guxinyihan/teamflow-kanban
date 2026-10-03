"""Task domain regressions: authorization, atomic ordering, WIP and subresources."""
from concurrent.futures import ThreadPoolExecutor

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
    headers = users["owner"]["headers"]
    for target, index in [(board["column_ids"][0], 0), (board["column_ids"][0], 3), (board["column_ids"][1], 0)]:
        snapshot = state(client, users, board)
        response = client.post(f"/api/tasks/{tasks[2]['id']}/move", json={"target_column_id": target, "target_index": index, "expected_revision": snapshot["revision"]}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["revision"] > snapshot["revision"]
        assert_order(state(client, users, board))


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
