from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..activity.service import commit_board
from ..auth.deps import get_current_user
from ..authorization.policy import board_permissions
from ..database import get_db
from ..serialization import attachment_dict
from ..tasks.service import authorized_task, locked_task
from .service import cleanup_files, private_path, store_upload

router = APIRouter()
task_router = APIRouter()


@task_router.post("/{task_id}/attachments/", status_code=201)
async def upload_attachment(task_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    authorized_task(db, task_id, user, edit=True)
    metadata = await store_upload(file)
    committed = False
    try:
        board, task = locked_task(db, task_id, user)
        attachment = models.Attachment(**metadata, filename=metadata["original_name"], file_path="", url="", task_id=task.id, user_id=user.id)
        db.add(attachment)
        task.version += 1
        db.flush()
        attachment.url = f"/api/attachments/{attachment.id}/download"
        await commit_board(db, board, user, "attachment_added", "attachment", attachment.id,
                           {"task_id": task.id, "title": task.title, "filename": attachment.original_name})
        committed = True
        return attachment_dict(attachment)
    except Exception:
        if not committed:
            db.rollback()
            cleanup_files([metadata["storage_name"]])
        raise
    finally:
        await file.close()


@task_router.get("/{task_id}/attachments/")
def list_attachments(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return [attachment_dict(attachment) for attachment in authorized_task(db, task_id, user).attachments]


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(404, detail="Attachment not found")
    authorized_task(db, attachment.task_id, user)
    path = private_path(attachment.storage_name)
    if not path.is_file():
        raise HTTPException(404, detail="Attachment bytes are unavailable")
    return FileResponse(path, media_type=attachment.content_type or "application/octet-stream",
                        filename=attachment.original_name or attachment.filename or "attachment",
                        content_disposition_type="attachment", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@task_router.delete("/{task_id}/attachments/{attachment_id}")
async def delete_attachment(task_id: int, attachment_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    attachment = db.query(models.Attachment).filter(models.Attachment.id == attachment_id, models.Attachment.task_id == task.id).first()
    if attachment is None:
        raise HTTPException(404, detail="Attachment not found")
    if attachment.user_id != user.id and not board_permissions(db, board, user)["can_admin"]:
        raise HTTPException(403, detail="Only uploader or board administrator may delete it")
    key, filename = attachment.storage_name, attachment.original_name or attachment.filename
    db.delete(attachment)
    task.version += 1
    await commit_board(db, board, user, "attachment_deleted", "attachment", attachment_id,
                       {"task_id": task.id, "title": task.title, "filename": filename})
    cleanup_files([key] if key else [])
    return {"message": "Attachment deleted"}
