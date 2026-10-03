"""Database-backed serialization; no process-local mutex pretends to protect SQL."""
from fastapi import HTTPException
from sqlalchemy import update, select
from .models import Board, Team

def board_lock(db, board_id, expected_revision=None):
    statement = update(Board).where(Board.id == board_id)
    if expected_revision is not None:
        statement = statement.where(Board.revision == expected_revision)
    result = db.execute(statement.values(revision=Board.revision + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        revision = db.scalar(select(Board.revision).where(Board.id == board_id))
        if revision is None:
            raise HTTPException(404, "Board not found")
        raise HTTPException(409, {"code": "stale_revision", "current_revision": revision, "revision": revision,
                                  "message": "The board changed. Reload and try again."})
    db.expire_all()
    return db.get(Board, board_id)

def team_lock(db, team_id):
    result = db.execute(update(Team).where(Team.id == team_id).values(
        membership_revision=Team.membership_revision + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(404, "Team not found")
    db.expire_all()
    return db.get(Team, team_id)
