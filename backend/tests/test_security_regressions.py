"""Release regressions for upstream's guessed-ID and public-write defects."""
import pytest


@pytest.mark.parametrize("resource", ["labels", "comments", "attachments"])
def test_anonymous_task_subresources_require_auth(client, users, board, resource):
    response = client.post(
        f"/api/tasks/?board_id={board['board_id']}",
        json={"title": "Requirements Specification", "column_id": board["column_ids"][0]},
        headers=users["owner"]["headers"],
    )
    assert response.status_code in (200, 201), response.text
    task_id = response.json()["id"]
    assert client.get(f"/api/tasks/{task_id}/{resource}/").status_code == 401


def test_outsider_cannot_write_public_read_board(client, users, board):
    owner = users["owner"]["headers"]
    response = client.patch(
        f"/api/boards/{board['board_id']}",
        json={"visibility": "public-read"}, headers=owner,
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/boards/{board['board_id']}/state", headers=users["outsider"]["headers"]).status_code == 200
    response = client.post(
        f"/api/tasks/?board_id={board['board_id']}",
        json={"title": "Unauthorized write", "column_id": board["column_ids"][0]},
        headers=users["outsider"]["headers"],
    )
    assert response.status_code == 403
    state = client.get(f"/api/boards/{board['board_id']}/state", headers=owner).json()
    assert not any(task["title"] == "Unauthorized write" for task in state["tasks"])


def test_task_move_requires_revision_and_is_domain_operation(client, users, board):
    headers = users["owner"]["headers"]
    created = client.post(
        f"/api/tasks/?board_id={board['board_id']}",
        json={"title": "Database Schema", "column_id": board["column_ids"][0]},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    task_id = created.json()["id"]
    state = client.get(f"/api/boards/{board['board_id']}/state", headers=headers).json()
    response = client.post(
        f"/api/tasks/{task_id}/move",
        json={"target_column_id": board["column_ids"][1], "target_index": 0, "expected_revision": state["revision"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["task"]["column_id"] == board["column_ids"][1]
    stale = client.post(
        f"/api/tasks/{task_id}/move",
        json={"target_column_id": board["column_ids"][0], "target_index": 0, "expected_revision": state["revision"]},
        headers=headers,
    )
    assert stale.status_code == 409
