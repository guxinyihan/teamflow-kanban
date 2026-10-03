"""Canonical zero-based ordering inside a serialized board transaction."""
from fastapi import HTTPException
from sqlalchemy import func

from .. import models


def column_for_board(db, column_id, board_id):
    column = db.get(models.BoardColumn, column_id)
    if column is None or column.board_id != board_id:
        raise HTTPException(422, detail={"code": "invalid_column", "message": "Column must belong to this board"})
    return column


def active_tasks(db, board_id, column_id):
    return db.query(models.Task).filter(
        models.Task.board_id == board_id,
        models.Task.column_id == column_id,
        models.Task.is_archived.is_(False),
    ).order_by(models.Task.position, models.Task.id).all()


def require_capacity(db, board, column, increase=1):
    current = db.query(func.count(models.Task.id)).filter(
        models.Task.board_id == board.id,
        models.Task.column_id == column.id,
        models.Task.is_archived.is_(False),
    ).scalar()
    if column.wip_limit is not None and increase > 0 and current + increase > column.wip_limit:
        raise HTTPException(409, detail={
            "code": "wip_limit", "message": "Column WIP limit would be exceeded",
            "column_id": column.id, "limit": column.wip_limit, "current": current,
            "revision": board.revision - 1,
        })


def write_order(db, board_id, ordered_columns):
    """Park affected rows above existing positions before canonical updates.

    Immediate unique indexes apply on SQLite and PostgreSQL. Distinct positive
    temporary values avoid collisions regardless of ORM update statement order.
    The caller commits once; parked positions are never externally visible.
    """
    tasks = {task.id: task for rows in ordered_columns.values() for task in rows}
    if not tasks:
        return
    maximum = db.query(func.max(models.Task.position)).filter(models.Task.board_id == board_id).scalar() or 0
    offset = maximum + len(tasks) + 1
    for index, task in enumerate(tasks.values()):
        task.position = offset + index
    db.flush()
    for column_id, rows in ordered_columns.items():
        for position, task in enumerate(rows):
            task.column_id = column_id
            task.position = position
            task.status = f"column:{column_id}"
    db.flush()


def move(db, board, task, target_column_id, target_index):
    if task.is_archived:
        raise HTTPException(409, detail={"code": "archived_task", "message": "Restore task before moving it"})
    target = column_for_board(db, target_column_id, board.id)
    source_column = task.column_id
    source_rows = active_tasks(db, board.id, source_column)
    destination_rows = source_rows if source_column == target.id else active_tasks(db, board.id, target.id)
    destination_rows = [row for row in destination_rows if row.id != task.id]
    if target_index > len(destination_rows):
        raise HTTPException(422, detail={"code": "invalid_index", "message": "Index is outside the target column"})
    if target.id != source_column:
        require_capacity(db, board, target)
    if target.id == source_column and task.position == target_index:
        return False
    destination_rows.insert(target_index, task)
    columns = {target.id: destination_rows}
    if target.id != source_column:
        columns[source_column] = [row for row in source_rows if row.id != task.id]
    write_order(db, board.id, columns)
    task.version += 1
    return True
