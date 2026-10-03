"""Authoritative board snapshots, persisted columns and activity views."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..activity.service import commit_board
from ..auth.deps import get_current_user
from ..authorization.policy import board_permissions, require_board_admin, require_board_view
from ..database import get_db
from ..domain import board_lock
from ..serialization import activity_dict, board_dict, column_dict, task_dict, user_dict
from ..tasks.schemas import BoardUpdate, ColumnCreate, ColumnReorder, ColumnUpdate
from ..tasks.service import clear_ineligible_assignments

router = APIRouter()
columns_router = APIRouter()


def columns_with_counts(db, board_id):
    counts = dict(db.query(models.Task.column_id, func.count(models.Task.id)).filter(models.Task.board_id == board_id, models.Task.is_archived.is_(False)).group_by(models.Task.column_id).all())
    columns = db.query(models.BoardColumn).filter_by(board_id=board_id).order_by(models.BoardColumn.position).all()
    return [column_dict(column, counts.get(column.id, 0)) for column in columns]


@router.get("/{board_id}/state")
def board_state(board_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Under READ COMMITTED, a second revision read detects an intervening commit
    # so tasks/columns cannot be paired with the preceding revision.
    for _ in range(3):
        board = require_board_view(db, board_id, user)
        revision = board.revision
        permissions = board_permissions(db, board, user)
        columns = columns_with_counts(db, board.id)
        tasks = db.query(models.Task).filter_by(board_id=board.id).order_by(models.Task.column_id, models.Task.is_archived, models.Task.position, models.Task.id).all()
        serialized_tasks = [task_dict(task) for task in tasks]
        members = []
        if permissions["can_edit"]:
            for membership in db.query(models.TeamMember).filter_by(team_id=board.team_id).all():
                member_user = db.get(models.User, membership.user_id)
                if board_permissions(db, board, member_user)["can_edit"]:
                    members.append({**user_dict(member_user, False), "role": membership.role})
        projected_board = board_dict(db, board, user)
        final_revision = db.query(models.Board.revision).filter_by(id=board_id).scalar()
        if final_revision == revision:
            return {"board": projected_board, "columns": columns, "tasks": serialized_tasks,
                    "members": members, "revision": revision, "permissions": permissions}
        db.rollback()
    raise HTTPException(409, detail={"code": "stale_revision", "message": "Board changed while reading; reload state", "revision": final_revision})


@router.patch("/{board_id}")
async def update_board(board_id: int, body: BoardUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_admin(db, board_id, user)
    board = board_lock(db, board_id)
    require_board_admin(db, board_id, user)
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(key, "") is None for key in ("name", "visibility")):
        raise HTTPException(422, detail="Board name and visibility cannot be null")
    for key, value in changes.items():
        setattr(board, key, value)
    board.is_public = board.visibility == "public-read"
    if "visibility" in changes:
        db.flush()
        clear_ineligible_assignments(db, board, user, "board_visibility_changed")
    await commit_board(db, board, user, "board_updated", "board", board.id, {"name": board.name})
    return board_dict(db, board, user)


@router.delete("/{board_id}")
async def delete_board(board_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from .teams import delete_board as delete_team_board
    board = require_board_admin(db, board_id, user)
    return await delete_team_board(board.team_id, board_id, db, user)


@router.get("/{board_id}/columns")
def list_columns(board_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_view(db, board_id, user)
    return columns_with_counts(db, board_id)


@router.post("/{board_id}/columns", status_code=201)
async def create_column(board_id: int, body: ColumnCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_admin(db, board_id, user)
    board = board_lock(db, board_id)
    require_board_admin(db, board_id, user)
    count = db.query(func.count(models.BoardColumn.id)).filter_by(board_id=board.id).scalar()
    column = models.BoardColumn(board_id=board.id, position=count, **body.model_dump())
    db.add(column)
    db.flush()
    await commit_board(db, board, user, "column_created", "column", column.id, {"name": column.name})
    return column_dict(column)


@router.post("/{board_id}/columns/reorder")
@router.put("/{board_id}/columns/reorder")
async def reorder_columns(board_id: int, body: ColumnReorder, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_admin(db, board_id, user)
    board = board_lock(db, board_id, body.expected_revision)
    require_board_admin(db, board_id, user)
    columns = db.query(models.BoardColumn).filter_by(board_id=board.id).order_by(models.BoardColumn.position).all()
    if len(body.column_ids) != len(columns) or len(set(body.column_ids)) != len(columns) or set(body.column_ids) != {column.id for column in columns}:
        raise HTTPException(422, detail="Reorder must contain every board column exactly once")
    offset = len(columns) + max([column.position for column in columns] + [0]) + 1
    for index, column in enumerate(columns):
        column.position = offset + index
    db.flush()
    by_id = {column.id: column for column in columns}
    for index, column_id in enumerate(body.column_ids):
        by_id[column_id].position = index
    await commit_board(db, board, user, "columns_reordered", "board", board.id)
    return columns_with_counts(db, board.id)


async def edit_column(column_id, body, db, user, board_id=None):
    column = db.get(models.BoardColumn, column_id)
    if column is None or (board_id is not None and column.board_id != board_id):
        raise HTTPException(404, detail="Column not found")
    require_board_admin(db, column.board_id, user)
    board = board_lock(db, column.board_id)
    require_board_admin(db, board.id, user)
    column = db.get(models.BoardColumn, column_id)
    changes = body.model_dump(exclude_unset=True)
    count = db.query(func.count(models.Task.id)).filter(models.Task.column_id == column.id, models.Task.is_archived.is_(False)).scalar()
    if "wip_limit" in changes and changes["wip_limit"] is not None and changes["wip_limit"] < count:
        raise HTTPException(409, detail={"code": "wip_limit", "message": "WIP limit cannot be below current active count", "column_id": column.id, "current": count, "limit": changes["wip_limit"], "revision": board.revision - 1})
    if "name" in changes and changes["name"] is None:
        raise HTTPException(422, detail="Column name cannot be null")
    for key, value in changes.items():
        setattr(column, key, value)
    await commit_board(db, board, user, "wip_limit_changed" if "wip_limit" in changes else "column_updated", "column", column.id, {"name": column.name, "wip_limit": column.wip_limit})
    return column_dict(column, count)


@router.patch("/{board_id}/columns/{column_id}")
async def nested_edit_column(board_id: int, column_id: int, body: ColumnUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return await edit_column(column_id, body, db, user, board_id)


@columns_router.patch("/{column_id}")
async def canonical_edit_column(column_id: int, body: ColumnUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return await edit_column(column_id, body, db, user)


async def delete_column(column_id, db, user, board_id=None):
    column = db.get(models.BoardColumn, column_id)
    if column is None or (board_id is not None and column.board_id != board_id):
        raise HTTPException(404, detail="Column not found")
    require_board_admin(db, column.board_id, user)
    board = board_lock(db, column.board_id)
    require_board_admin(db, board.id, user)
    column = db.get(models.BoardColumn, column_id)
    if db.query(models.Task.id).filter_by(column_id=column.id).first() is not None:
        raise HTTPException(409, detail={"code": "column_not_empty", "message": "Move or delete all active and archived tasks before deleting a column"})
    columns = db.query(models.BoardColumn).filter_by(board_id=board.id).order_by(models.BoardColumn.position).all()
    if len(columns) <= 1:
        raise HTTPException(409, detail="Board must retain at least one column")
    name = column.name
    db.delete(column)
    db.flush()
    remaining = [item for item in columns if item.id != column_id]
    for index, item in enumerate(remaining):
        item.position = len(columns) * 2 + index
    db.flush()
    for index, item in enumerate(remaining):
        item.position = index
    await commit_board(db, board, user, "column_deleted", "column", column_id, {"name": name})
    return {"message": "Column deleted"}


@router.delete("/{board_id}/columns/{column_id}")
async def nested_delete_column(board_id: int, column_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return await delete_column(column_id, db, user, board_id)


@columns_router.delete("/{column_id}")
async def canonical_delete_column(column_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return await delete_column(column_id, db, user)


@router.get("/{board_id}/activity")
def list_activity(board_id: int, limit: int = Query(100, ge=1, le=200), before_id: int | None = Query(None, ge=1), db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_board_view(db, board_id, user)
    query = db.query(models.ActivityEvent).filter_by(board_id=board_id)
    if before_id is not None:
        query = query.filter(models.ActivityEvent.id < before_id)
    return [activity_dict(event) for event in query.order_by(models.ActivityEvent.id.desc()).limit(limit).all()]
