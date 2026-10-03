from datetime import datetime, timezone

from fastapi import HTTPException

from .. import models
from ..authorization.policy import require_board_edit, require_board_view
from ..domain import board_lock
from .ordering import active_tasks, column_for_board, require_capacity, write_order


def authorized_task(db, task_id, user, edit=False):
    task = db.get(models.Task, task_id)
    if task is None:
        raise HTTPException(404, detail="Task not found")
    (require_board_edit if edit else require_board_view)(db, task.board_id, user)
    return task


def locked_task(db, task_id, user, expected_revision=None):
    task = authorized_task(db, task_id, user, edit=True)
    board = board_lock(db, task.board_id, expected_revision)
    require_board_edit(db, board.id, user)
    task = db.get(models.Task, task_id)
    if task is None:
        raise HTTPException(404, detail="Task not found")
    return board, task


def assign(db, board, task, assignee_id):
    if assignee_id is None:
        task.assignee_id = None
        task.assigned_to = []
        return
    user = db.get(models.User, assignee_id)
    if user is None:
        raise HTTPException(422, detail="Assignee does not exist")
    try:
        require_board_edit(db, board.id, user)
    except HTTPException:
        raise HTTPException(422, detail={"code": "invalid_assignee", "message": "Assignee must be allowed to work on this board"})
    task.assignee_id = user.id
    task.assigned_to = [user]


def archive(db, board, task, archived):
    if task.is_archived == archived:
        return
    column = column_for_board(db, task.column_id, board.id)
    if archived:
        task.is_archived = True
        task.archived_at = datetime.now(timezone.utc)
        db.flush()
        write_order(db, board.id, {column.id: active_tasks(db, board.id, column.id)})
    else:
        require_capacity(db, board, column)
        rows = active_tasks(db, board.id, column.id)
        task.position = max([row.position for row in rows] + [task.position or 0]) + 1
        task.is_archived = False
        task.archived_at = None
        db.flush()
        write_order(db, board.id, {column.id: rows + [task]})


def comment_dict(comment):
    return {"id": comment.id, "content": comment.content,
            "task_id": comment.task_id, "user_id": comment.user_id,
            "user_name": comment.user_name, "created_at": comment.created_at,
            "updated_at": comment.updated_at}


def label_dict(label):
    return {"id": label.id, "name": label.name, "color": label.color, "board_id": label.board_id}
