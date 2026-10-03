"""Real WebSocket clients verify committed events and board channel isolation."""
from datetime import timedelta

import anyio
import pytest
from starlette.websockets import WebSocketDisconnect


def authorize(socket, user, board_id):
    socket.send_json({"token": user["token"]})
    ready = socket.receive_json()
    assert ready["type"] == "ready"
    assert ready["board_id"] == board_id
    assert isinstance(ready["revision"], int)
    return ready


def assert_no_pending_frame(socket):
    # TestClient's memory receive stream makes absence deterministic without
    # an unbounded receive() or an arbitrary sleeping test thread.
    with pytest.raises(anyio.WouldBlock):
        socket._send_rx.receive_nowait()


@pytest.mark.parametrize("identity", ["invalid", "outsider", "expired"])
def test_socket_rejects_missing_expired_or_unauthorized_identity(client, users, board, identity):
    token = "not-a-token"
    if identity == "outsider":
        token = users["outsider"]["token"]
    elif identity == "expired":
        from app.auth.utils import create_access_token
        token = create_access_token({"sub": users["owner"]["user"]["id"]}, timedelta(seconds=-1))
    with client.websocket_connect(f"/api/boards/{board['board_id']}/ws") as socket:
        socket.send_json({"token": token})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1008


def test_socket_rejects_untrusted_origin(client, users, board):
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(f"/api/boards/{board['board_id']}/ws", headers={"Origin": "https://untrusted.example"}):
            pass
    assert error.value.code == 1008


def test_two_clients_receive_only_their_boards_committed_events(client, users, board, db):
    owner_headers = users["owner"]["headers"]
    other = client.post(f"/api/teams/{board['team_id']}/boards", headers=owner_headers,
                        json={"name": "Different board", "visibility": "team"})
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]
    url = f"/api/boards/{board['board_id']}/ws"
    with client.websocket_connect(url) as owner_socket, client.websocket_connect(url) as member_socket, \
            client.websocket_connect(f"/api/boards/{other_id}/ws") as other_socket:
        ready = authorize(owner_socket, users["owner"], board["board_id"])
        authorize(member_socket, users["member"], board["board_id"])
        authorize(other_socket, users["owner"], other_id)
        created = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=owner_headers,
                              json={"title": "Committed task", "column_id": board["column_ids"][0]})
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        event = owner_socket.receive_json()
        assert event == member_socket.receive_json()
        assert event["type"] == "task.created"
        assert event["board_id"] == board["board_id"]
        assert event["revision"] > ready["revision"]
        from app.models import Task, Board
        db.expire_all()
        assert db.get(Task, task_id).title == "Committed task"
        assert db.get(Board, board["board_id"]).revision == event["revision"]
        assert_no_pending_frame(other_socket)
        moved = client.post(f"/api/tasks/{task_id}/move", headers=owner_headers, json={
            "target_column_id": board["column_ids"][1], "target_index": 0,
            "expected_revision": event["revision"],
        })
        assert moved.status_code == 200, moved.text
        move_event = owner_socket.receive_json()
        assert move_event == member_socket.receive_json()
        assert move_event["type"] == "task.moved"
        assert move_event["revision"] > event["revision"]
        comment = client.post(f"/api/tasks/{task_id}/comments/", headers=users["member"]["headers"],
                              json={"content": "API integration reviewed", "task_id": task_id})
        assert comment.status_code == 201, comment.text
        comment_event = owner_socket.receive_json()
        assert comment_event == member_socket.receive_json()
        assert comment_event["type"] == "comment.created"
        assert comment_event["revision"] > move_event["revision"]
        assert_no_pending_frame(other_socket)


def test_failed_mutation_does_not_broadcast_success(client, users, board):
    with client.websocket_connect(f"/api/boards/{board['board_id']}/ws") as socket:
        authorize(socket, users["owner"], board["board_id"])
        denied = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=users["outsider"]["headers"],
                             json={"title": "Must not broadcast", "column_id": board["column_ids"][0]})
        assert denied.status_code == 403
        assert_no_pending_frame(socket)


def test_membership_removal_closes_existing_board_socket(client, users, board):
    with client.websocket_connect(f"/api/boards/{board['board_id']}/ws") as socket:
        authorize(socket, users["member"], board["board_id"])
        removed = client.delete(f"/api/teams/{board['team_id']}/members/{users['member']['user']['id']}",
                                headers=users["owner"]["headers"])
        assert removed.status_code == 200, removed.text
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1008


def test_database_commit_failure_rolls_back_task_activity_revision_and_broadcast(client, users, board, db,
                                                                             session_factory, monkeypatch):
    import sqlalchemy as sa
    from sqlalchemy.exc import OperationalError
    from app.models import ActivityEvent, Board, Task

    revision = db.get(Board, board["board_id"]).revision
    before = db.scalar(sa.select(sa.func.count()).select_from(ActivityEvent).where(ActivityEvent.board_id == board["board_id"]))
    db.rollback()

    def failed_commit(_session):
        raise OperationalError("COMMIT", {}, RuntimeError("Injected database commit failure"))

    with client.websocket_connect(f"/api/boards/{board['board_id']}/ws") as socket:
        authorize(socket, users["owner"], board["board_id"])
        with monkeypatch.context() as patch:
            patch.setattr(session_factory.class_, "commit", failed_commit)
            response = client.post(f"/api/tasks/?board_id={board['board_id']}", headers=users["owner"]["headers"],
                                   json={"title": "Rolled back database mutation", "column_id": board["column_ids"][0]})
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"
        assert_no_pending_frame(socket)
    db.expire_all()
    assert db.get(Board, board["board_id"]).revision == revision
    assert db.scalar(sa.select(sa.func.count()).select_from(Task).where(Task.title == "Rolled back database mutation")) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(ActivityEvent).where(ActivityEvent.board_id == board["board_id"])) == before
