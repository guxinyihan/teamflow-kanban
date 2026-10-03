"""Private attachment authorization, validation and cleanup release gates."""
import pytest

def create(client, users, board):
    response = client.post(f"/api/tasks/?board_id={board['board_id']}", json={"title": "Attachment test", "column_id": board["column_ids"][0]}, headers=users["owner"]["headers"])
    assert response.status_code in (200, 201), response.text
    return response.json()


def upload(client, headers, task_id, name="notes.txt", content=b"Safe plain text", mime="text/plain"):
    return client.post(f"/api/tasks/{task_id}/attachments/", files={"file": (name, content, mime)}, headers=headers)


def test_attachment_is_private_and_only_authorized_users_download(client, users, board):
    task = create(client, users, board)
    headers = users["owner"]["headers"]
    response = upload(client, headers, task["id"])
    assert response.status_code in (200, 201), response.text
    attachment = response.json()
    assert "file_path" not in attachment and "storage_name" not in attachment
    path = f"/api/attachments/{attachment['id']}/download"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=users["outsider"]["headers"]).status_code == 403
    downloaded = client.get(path, headers=headers)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == b"Safe plain text"
    assert "attachment" in downloaded.headers["content-disposition"]
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert client.get("/uploads/notes.txt", headers=headers).status_code == 404
    assert client.delete(f"/api/tasks/{task['id']}/attachments/{attachment['id']}", headers=users["outsider"]["headers"]).status_code == 403
    assert client.delete(f"/api/tasks/{task['id']}/attachments/{attachment['id']}", headers=headers).status_code == 200
    assert client.get(path, headers=headers).status_code == 404


@pytest.mark.parametrize("name,content,mime", [
    ("../escape.txt", b"safe", "text/plain"),
    ("C:\\escape.txt", b"safe", "text/plain"),
    ("payload.html", b"<script>alert(1)</script>", "text/html"),
    ("payload.svg", b"<svg onload='alert(1)'/>", "image/svg+xml"),
    ("fake.png", b"not a png", "image/png"),
    ("fake.pdf", b"not a PDF", "application/pdf"),
    ("notes.txt", b"<html><script>alert(1)</script></html>", "text/plain"),
])
def test_unsafe_filename_or_content_is_rejected(client, users, board, name, content, mime):
    task = create(client, users, board)
    response = upload(client, users["owner"]["headers"], task["id"], name, content, mime)
    assert response.status_code in (400, 415, 422), response.text
    assert client.get(f"/api/tasks/{task['id']}/attachments/", headers=users["owner"]["headers"]).json() == []


def test_unrelated_user_cannot_upload_to_guessed_task(client, users, board):
    task = create(client, users, board)
    response = upload(client, users["outsider"]["headers"], task["id"])
    assert response.status_code == 403
    assert client.get(f"/api/tasks/{task['id']}/attachments/", headers=users["owner"]["headers"]).json() == []


def test_oversized_stream_is_rejected(client, users, board):
    task = create(client, users, board)
    response = upload(client, users["owner"]["headers"], task["id"], content=b"a" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413, response.text
    assert client.get(f"/api/tasks/{task['id']}/attachments/", headers=users["owner"]["headers"]).json() == []
