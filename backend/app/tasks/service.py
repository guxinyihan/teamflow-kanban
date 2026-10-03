from datetime import datetime, timezone

from fastapi import HTTPException

from .. import models
from ..authorization.policy import board_permissions, require_board_edit, require_board_view
from ..activity.service import record_event
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


def clear_ineligible_assignments(db, board, actor, reason):
    """Keep assignments consistent with policy after a visibility/role change.

    The caller holds the board lock and has flushed the changed policy. Clears,
    versions and activity participate in the caller's single transaction.
    """
    tasks = db.query(models.Task).filter(
        models.Task.board_id == board.id, models.Task.assignee_id.is_not(None)
    ).all()
    for task in tasks:
        assignee = db.get(models.User, task.assignee_id)
        if assignee and board_permissions(db, board, assignee)["can_edit"]:
            continue
        previous_id = task.assignee_id
        task.assignee_id = None
        task.assigned_to = []
        task.version += 1
        record_event(db, actor, "task_assigned", "task", task.id, board=board,
                     details={"title": task.title, "assignee_id": None,
                              "assignee_name": "Unassigned", "previous_assignee_id": previous_id,
                              "reason": reason})


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
