"""Authorized inherited task features and atomic task domain operations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..activity.service import commit_board, record_event
from ..auth.deps import get_current_user
from ..authorization.policy import board_permissions, require_board_edit, require_board_view
from ..database import get_db
from ..domain import board_lock
from ..serialization import task_dict
from ..tasks import schemas
from ..tasks.ordering import active_tasks, column_for_board, move, require_capacity, write_order
from ..tasks.service import archive, assign, authorized_task, comment_dict, label_dict, locked_task
from ..attachments.router import task_router as attachment_routes

router = APIRouter()
router.include_router(attachment_routes)


@router.post("/", status_code=201)
async def create_task(body: schemas.TaskCreate, board_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_edit(db, board_id, user)
    board = board_lock(db, board_id)
    require_board_edit(db, board_id, user)
    column = column_for_board(db, body.column_id, board_id)
    require_capacity(db, board, column)
    rows = active_tasks(db, board_id, column.id)
    task = models.Task(**body.model_dump(exclude={"assignee_id"}), board_id=board_id, creator_id=user.id,
                       position=len(rows), status=f"column:{column.id}", checklist=[], is_archived=False, version=1)
    db.add(task)
    assign(db, board, task, body.assignee_id)
    db.flush()
    await commit_board(db, board, user, "task_created", "task", task.id, {"title": task.title})
    return task_dict(task)


@router.get("/")
def read_tasks(board_id: int, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_view(db, board_id, user)
    tasks = db.query(models.Task).filter(models.Task.board_id == board_id).order_by(models.Task.column_id, models.Task.position, models.Task.id).offset(skip).limit(limit).all()
    return [task_dict(task) for task in tasks]


@router.get("/{task_id}")
def read_task(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return task_dict(authorized_task(db, task_id, user))


@router.put("/{task_id}")
@router.patch("/{task_id}")
async def update_task(task_id: int, body: schemas.TaskUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user, body.expected_revision)
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    for key in ("title", "priority", "is_archived"):
        if key in changes and changes[key] is None:
            raise HTTPException(422, detail=f"{key} cannot be null")
    changes = {key: value for key, value in changes.items() if getattr(task, key) != value}
    if not changes:
        db.rollback()
        return task_dict(db.get(models.Task, task_id))
    changed_fields = list(changes)
    action = "task_updated"
    assignment_details = None
    if "assignee_id" in changes:
        assignee_id = changes.pop("assignee_id")
        assign(db, board, task, assignee_id)
        assignee = db.get(models.User, assignee_id) if assignee_id is not None else None
        assignment_details = {"title": changes.get("title", task.title), "assignee_id": assignee_id,
                              "assignee_name": (assignee.full_name or assignee.username) if assignee else "Unassigned"}
        if not changes:
            action = "task_assigned"
    archived = changes.pop("is_archived", None)
    if archived is not None and archived != task.is_archived:
        archive(db, board, task, archived)
        action = "task_archived" if archived else "task_restored"
    for key, value in changes.items():
        setattr(task, key, value)
    task.version += 1
    if assignment_details is not None and action != "task_assigned":
        record_event(db, user, "task_assigned", "task", task.id, board=board, details=assignment_details)
    details = assignment_details if action == "task_assigned" else {"title": task.title, "changed_fields": changed_fields}
    await commit_board(db, board, user, action, "task", task.id, details)
    return task_dict(task)


@router.post("/{task_id}/move")
async def move_task(task_id: int, body: schemas.TaskMove, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user, body.expected_revision)
    if body.expected_version is not None and body.expected_version != task.version:
        raise HTTPException(409, detail={"code": "stale_version", "message": "Task version changed; reload state", "version": task.version, "revision": board.revision - 1})
    source = task.column_id
    source_name = db.get(models.BoardColumn, source).name
    changed = move(db, board, task, body.target_column_id, body.target_index)
    if not changed:
        board_id = board.id
        db.rollback()
        return {"task": task_dict(db.get(models.Task, task_id)), "revision": db.get(models.Board, board_id).revision}
    revision = await commit_board(db, board, user, "task_moved", "task", task.id,
                                  {"title": task.title, "source_column_id": source, "source_column_name": source_name,
                                   "target_column_id": task.column_id, "target_column_name": db.get(models.BoardColumn, task.column_id).name,
                                   "target_index": task.position})
    return {"task": task_dict(task), "revision": revision}


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from ..attachments.service import cleanup_files
    board, task = locked_task(db, task_id, user)
    paths = list(task.attachments)
    column_id, title = task.column_id, task.title
    db.delete(task)
    db.flush()
    write_order(db, board.id, {column_id: active_tasks(db, board.id, column_id)})
    await commit_board(db, board, user, "task_deleted", "task", task_id, {"title": title})
    cleanup_files(paths)
    return {"message": "Task deleted"}


@router.post("/{task_id}/labels/", status_code=201)
async def add_label(task_id: int, body: schemas.LabelCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    normalized = body.name.casefold()
    label = db.query(models.Label).filter(models.Label.board_id == board.id, models.Label.normalized_name == normalized).first()
    if label is None:
        label = models.Label(name=body.name, normalized_name=normalized, color=body.color, board_id=board.id)
        db.add(label)
        db.flush()
    if label not in task.labels:
        task.labels.append(label)
        task.version += 1
    else:
        label_id = label.id
        db.rollback()
        return label_dict(db.get(models.Label, label_id))
    await commit_board(db, board, user, "label_added", "task", task.id, {"title": task.title, "label": label.name})
    return label_dict(label)


@router.get("/{task_id}/labels/")
def get_labels(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return [label_dict(label) for label in authorized_task(db, task_id, user).labels]


@router.delete("/{task_id}/labels/{label_id}")
async def remove_label(task_id: int, label_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    label = next((label for label in task.labels if label.id == label_id), None)
    if label is None or label.board_id != board.id:
        raise HTTPException(404, detail="Label not applied to this task")
    task.labels.remove(label)
    task.version += 1
    await commit_board(db, board, user, "label_removed", "task", task.id, {"title": task.title, "label": label.name})
    return {"message": "Label removed"}


@router.post("/{task_id}/comments/", status_code=201)
async def add_comment(task_id: int, body: schemas.CommentCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    if body.task_id is not None and body.task_id != task_id:
        raise HTTPException(422, detail="Comment task ID does not match URL")
    comment = models.Comment(content=body.content, task_id=task.id, user_id=user.id, user=user)
    db.add(comment)
    task.version += 1
    db.flush()
    await commit_board(db, board, user, "comment_added", "comment", comment.id, {"task_id": task.id, "title": task.title})
    return comment_dict(comment)


@router.get("/{task_id}/comments/")
def get_comments(task_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return [comment_dict(comment) for comment in authorized_task(db, task_id, user).comments]


@router.delete("/{task_id}/comments/{comment_id}")
async def delete_comment(task_id: int, comment_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id, models.Comment.task_id == task.id).first()
    if comment is None:
        raise HTTPException(404, detail="Comment not found")
    if comment.user_id != user.id and not board_permissions(db, board, user)["can_admin"]:
        raise HTTPException(403, detail="Only comment author or board administrator may delete it")
    db.delete(comment)
    task.version += 1
    await commit_board(db, board, user, "comment_deleted", "comment", comment_id, {"task_id": task.id, "title": task.title})
    return {"message": "Comment deleted"}


@router.post("/{task_id}/checklist/")
async def add_checklist_item(task_id: int, body: schemas.ChecklistCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    items = task.checklist or []
    next_id = max([item["id"] for item in items] + [board.revision * 1000000]) + 1
    task.checklist = items + [{"id": next_id, "content": body.content, "is_completed": False}]
    task.version += 1
    await commit_board(db, board, user, "checklist_added", "task", task.id, {"title": task.title})
    return task_dict(task)


@router.put("/{task_id}/checklist/{item_id}/toggle/")
async def toggle_checklist_item(task_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    if not any(item["id"] == item_id for item in task.checklist or []):
        raise HTTPException(404, detail="Checklist item not found")
    task.checklist = [{**item, "is_completed": not item["is_completed"]} if item["id"] == item_id else dict(item) for item in task.checklist]
    task.version += 1
    await commit_board(db, board, user, "checklist_toggled", "task", task.id, {"title": task.title})
    return task_dict(task)


@router.delete("/{task_id}/checklist/{item_id}")
async def delete_checklist_item(task_id: int, item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    board, task = locked_task(db, task_id, user)
    if not any(item["id"] == item_id for item in task.checklist or []):
        raise HTTPException(404, detail="Checklist item not found")
    task.checklist = [dict(item) for item in task.checklist if item["id"] != item_id]
    task.version += 1
    await commit_board(db, board, user, "checklist_deleted", "task", task.id, {"title": task.title})
    return task_dict(task)
