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


def test_missing_physical_attachment_can_be_deleted(client, users, board, db):
    from app.attachments.service import private_path
    from app.models import Attachment
    task = create(client, users, board)
    headers = users["owner"]["headers"]
    response = upload(client, headers, task["id"])
    attachment_id = response.json()["id"]
    item = db.get(Attachment, attachment_id)
    private_path(item.storage_name).unlink()
    assert client.get(f"/api/attachments/{attachment_id}/download", headers=headers).status_code == 404
    assert client.delete(f"/api/tasks/{task['id']}/attachments/{attachment_id}", headers=headers).status_code == 200


def test_legacy_import_copies_safe_bytes_and_preserves_original(client, users, board, db, tmp_path):
    from app.models import Attachment
    from scripts.import_legacy_attachments import import_legacy_attachments
    task = create(client, users, board)
    source = tmp_path / "legacy-uploads"
    source.mkdir()
    original = source / "old_notes.txt"
    original.write_bytes(b"Legacy project notes")
    attachment = Attachment(task_id=task["id"], user_id=users["owner"]["user"]["id"],
                            filename="notes.txt", original_name="notes.txt", file_path="legacy-uploads/old_notes.txt", url="/uploads/old_notes.txt")
    db.add(attachment)
    db.commit()
    report = import_legacy_attachments(db, source)
    assert report == {"imported": 1, "missing": 0, "unsupported": 0, "unsafe": 0}
    assert original.read_bytes() == b"Legacy project notes"
    path = f"/api/attachments/{attachment.id}/download"
    assert client.get(path, headers=users["owner"]["headers"]).content == b"Legacy project notes"
    assert client.get(path, headers=users["outsider"]["headers"]).status_code == 403


def test_legacy_import_rejects_path_escape(client, users, board, db, tmp_path):
    from app.models import Attachment
    from scripts.import_legacy_attachments import import_legacy_attachments
    task = create(client, users, board)
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "outside.txt").write_text("Outside approved legacy root", encoding="utf-8")
    attachment = Attachment(task_id=task["id"], user_id=users["owner"]["user"]["id"], filename="outside.txt", file_path="../outside.txt", url="/uploads/outside.txt")
    db.add(attachment)
    db.commit()
    assert import_legacy_attachments(db, source)["unsafe"] == 1
    assert attachment.storage_name is None


def test_failed_database_mutation_removes_staged_bytes(client, users, board, monkeypatch):
    from fastapi import HTTPException
    from app.attachments import router as attachment_router
    from app.attachments.service import storage_root
    task = create(client, users, board)
    async def failing_commit(*args, **kwargs):
        raise HTTPException(500, detail="Simulated database failure")
    monkeypatch.setattr(attachment_router, "commit_board", failing_commit)
    response = upload(client, users["owner"]["headers"], task["id"])
    assert response.status_code == 500
    assert list(storage_root().iterdir()) == []
    assert client.get(f"/api/tasks/{task['id']}/attachments/", headers=users["owner"]["headers"]).json() == []
