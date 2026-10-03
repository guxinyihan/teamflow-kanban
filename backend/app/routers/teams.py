"""Team and board membership operations share centralized policy and locks."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..database import get_db
from ..auth.deps import get_current_user
from .. import models as m, schemas as s
from ..authorization.policy import require_team, team_role, require_board_admin, require_board_view, board_permissions
from ..domain import team_lock, board_lock
from ..serialization import team_dict, board_dict, user_dict
from ..teams.service import create_team as build_team, create_board as build_board
from ..activity.service import record_event, commit_board
from ..realtime.manager import manager
from ..tasks.service import clear_ineligible_assignments

router = APIRouter()

def lock_team(db, team_id, user, roles=("owner", "admin")):
    require_team(db, team_id, user, roles)
    team = team_lock(db, team_id)
    require_team(db, team_id, user, roles)
    return team

def lock_team_boards(db, team):
    boards = db.scalars(select(m.Board).where(m.Board.team_id == team.id).order_by(m.Board.id)).all()
    return [board_lock(db, board.id) for board in boards]

async def announce_membership(boards):
    for board in boards:
        await manager.publish({"type": "board.membership_changed", "board_id": board.id, "revision": board.revision})

@router.get("/")
def list_teams(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    teams = db.query(m.Team).join(m.TeamMember).filter(m.TeamMember.user_id == user.id).order_by(m.Team.id).all()
    return [team_dict(db, team, user) for team in teams]

@router.post("/", status_code=201)
def create_team(data: s.TeamCreate, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    team = build_team(db, user, data.name, data.description)
    record_event(db, user, "team.created", "team", team.id, team=team, details={"name": team.name})
    db.commit()
    return team_dict(db, team, user)

@router.get("/{team_id}")
def get_team(team_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return team_dict(db, require_team(db, team_id, user), user)

@router.patch("/{team_id}")
def update_team(team_id: int, data: s.TeamUpdate, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    team = lock_team(db, team_id, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "name":
            if value is None or not value.strip():
                raise HTTPException(422, "Name is required")
            value = value.strip()
        setattr(team, key, value)
    record_event(db, user, "team.updated", "team", team.id, team=team, details={"name": team.name})
    db.commit()
    return team_dict(db, team, user)

@router.get("/{team_id}/members")
def get_members(team_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return team_dict(db, require_team(db, team_id, user), user)["members"]

@router.patch("/{team_id}/members/{user_id}")
async def update_member(team_id: int, user_id: int, data: s.MemberUpdate, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    team = lock_team(db, team_id, user, ("owner",))
    member = db.get(m.TeamMember, (team_id, user_id))
    if member is None:
        raise HTTPException(404, "Member not found")
    if user_id == team.owner_id:
        raise HTTPException(409, "Transfer ownership before changing the owner role")
    boards = lock_team_boards(db, team)
    member.role = data.role
    db.flush()
    for board in boards:
        clear_ineligible_assignments(db, board, user, "team_role_changed")
    record_event(db, user, "member.role_changed", "user", user_id, team=team, details={"role": data.role})
    db.commit()
    await announce_membership(boards)
    return {"user": user_dict(db.get(m.User, user_id)), "role": data.role}

@router.delete("/{team_id}/members/{user_id}")
async def remove_member(team_id: int, user_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    team = lock_team(db, team_id, user)
    target = db.get(m.TeamMember, (team_id, user_id))
    if target is None:
        raise HTTPException(404, "Member not found")
    if user_id == team.owner_id:
        raise HTTPException(409, "Transfer ownership before removing the owner")
    if target.role == "admin" and team_role(db, team_id, user) != "owner":
        raise HTTPException(403, "Only the owner manages administrators")
    boards = lock_team_boards(db, team)
    board_ids = [board.id for board in boards]
    for membership in db.query(m.BoardMember).filter(m.BoardMember.board_id.in_(board_ids), m.BoardMember.user_id == user_id):
        db.delete(membership)
    for task in db.query(m.Task).filter(m.Task.board_id.in_(board_ids)).all():
        if task.assignee_id == user_id:
            task.assignee_id = None
            task.version += 1
        task.assigned_to = [actor for actor in task.assigned_to if actor.id != user_id]
    now = datetime.now(timezone.utc)
    for invitation in db.query(m.Invitation).filter_by(team_id=team_id, created_by=user_id).all():
        if invitation.accepted_at is None:
            invitation.revoked_at = now
    db.delete(target)
    record_event(db, user, "member.removed", "user", user_id, team=team)
    db.commit()
    await announce_membership(boards)
    return {"message": "Member removed"}

@router.post("/{team_id}/transfer-ownership")
async def transfer_ownership(team_id: int, data: s.OwnershipTransfer, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    team = lock_team(db, team_id, user, ("owner",))
    if data.user_id == team.owner_id:
        raise HTTPException(409, "User already owns this team")
    target = db.get(m.TeamMember, (team_id, data.user_id))
    if target is None:
        raise HTTPException(400, "New owner must already belong to this team")
    boards = lock_team_boards(db, team)
    previous = db.get(m.TeamMember, (team_id, team.owner_id))
    previous.role = "admin"
    db.flush()
    target.role = "owner"
    team.owner_id = target.user_id
    record_event(db, user, "team.ownership_transferred", "team", team.id, team=team, details={"new_owner_id": target.user_id})
    db.commit()
    await announce_membership(boards)
    return team_dict(db, team, user)

@router.get("/{team_id}/boards")
def list_boards(team_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    require_team(db, team_id, user)
    boards = db.query(m.Board).filter_by(team_id=team_id).order_by(m.Board.id).all()
    return [board_dict(db, board, user) for board in boards if board_permissions(db, board, user)["can_view"]]

@router.post("/{team_id}/boards", status_code=201)
def create_board(team_id: int, data: s.BoardCreate, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    if data.team_id is not None and data.team_id != team_id:
        raise HTTPException(422, "URL and body team IDs must match")
    team = lock_team(db, team_id, user)
    board = build_board(db, team, user, data.name, data.description, data.visibility)
    record_event(db, user, "board.created", "board", board.id, board=board, details={"name": board.name})
    db.commit()
    return board_dict(db, board, user)

@router.get("/{team_id}/boards/{board_id}")
def get_board(team_id: int, board_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    board = require_board_view(db, board_id, user)
    if board.team_id != team_id:
        raise HTTPException(404, "Board not found")
    return board_dict(db, board, user)

@router.get("/{team_id}/boards/{board_id}/members")
def board_members(team_id: int, board_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return get_board(team_id, board_id, db, user)["members"]

@router.post("/{team_id}/boards/{board_id}/members", status_code=201)
async def add_board_member(team_id: int, board_id: int, data: s.BoardMemberCreate, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    board = require_board_admin(db, board_id, user)
    if board.team_id != team_id:
        raise HTTPException(404, "Board not found")
    # Team -> board order matches membership removal and prevents admission races.
    team_lock(db, team_id)
    board = board_lock(db, board_id)
    require_board_admin(db, board_id, user)
    if not db.get(m.TeamMember, (team_id, data.user_id)):
        raise HTTPException(400, "Board members must be team members")
    if db.get(m.BoardMember, (board_id, data.user_id)):
        raise HTTPException(409, "User is already a board member")
    db.add(m.BoardMember(board_id=board_id, user_id=data.user_id, role=data.role))
    await commit_board(db, board, user, "board.member_added", "user", data.user_id, {"role": data.role})
    return {"user": user_dict(db.get(m.User, data.user_id), False), "role": data.role}

@router.delete("/{team_id}/boards/{board_id}/members/{user_id}")
async def remove_board_member(team_id: int, board_id: int, user_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    board = require_board_admin(db, board_id, user)
    if board.team_id != team_id:
        raise HTTPException(404, "Board not found")
    team_lock(db, team_id)
    board = board_lock(db, board_id)
    require_board_admin(db, board_id, user)
    member = db.get(m.BoardMember, (board_id, user_id))
    if member is None:
        raise HTTPException(404, "Board member not found")
    db.delete(member)
    db.flush()
    target = db.get(m.User, user_id)
    if target and not board_permissions(db, board, target)["can_edit"]:
        for task in db.query(m.Task).filter_by(board_id=board_id, assignee_id=user_id):
            task.assignee_id = None
            task.assigned_to = []
            task.version += 1
    await commit_board(db, board, user, "board.member_removed", "user", user_id)
    return {"message": "Board member removed"}

def delete_board_data(db, board):
    storage_names = []
    for task in list(board.tasks):
        storage_names.extend(item.storage_name for item in task.attachments if item.storage_name)
        db.delete(task)
    db.flush()
    # Deleted cards must not remain in the parent's loaded cascade collection.
    db.expire(board, ["tasks"])
    db.delete(board)
    db.flush()
    return storage_names

def cleanup_storage(names):
    from ..attachments.service import cleanup_files
    cleanup_files(names)

@router.delete("/{team_id}/boards/{board_id}")
async def delete_board(team_id: int, board_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    board = require_board_admin(db, board_id, user)
    if board.team_id != team_id:
        raise HTTPException(404, "Board not found")
    team_lock(db, team_id)
    board = board_lock(db, board_id)
    require_board_admin(db, board_id, user)
    revision = board.revision
    names = delete_board_data(db, board)
    db.commit()
    cleanup_storage(names)
    await manager.publish({"type": "board.deleted", "board_id": board_id, "revision": revision})
    return {"message": "Board and its tasks deleted"}

@router.delete("/{team_id}")
async def delete_team(team_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    team = lock_team(db, team_id, user, ("owner",))
    boards = lock_team_boards(db, team)
    names = []
    for board in boards:
        names.extend(delete_board_data(db, board))
    db.expire(team, ["boards"])
    db.delete(team)
    db.commit()
    cleanup_storage(names)
    await announce_membership(boards)
    return {"message": "Team and its boards deleted"}
