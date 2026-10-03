"""One policy for HTTP, task subresources and WebSocket board eligibility."""
from fastapi import HTTPException
from ..models import Board, BoardMember, Team, TeamMember

def team_role(db, team_id, user):
    team = db.get(Team, team_id)
    member = db.get(TeamMember, (team_id, user.id)) if team else None
    if not member:
        return None
    return "owner" if team.owner_id == user.id else member.role

def require_team(db, team_id, user, roles=None):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    role = team_role(db, team_id, user)
    if role is None or (roles is not None and role not in roles):
        raise HTTPException(403, "Team permission required")
    return team

def board_permissions(db, board, user):
    role = team_role(db, board.team_id, user)
    member = db.get(BoardMember, (board.id, user.id)) if role else None
    admin = role in ("owner", "admin") or bool(member and member.role == "admin")
    edit = admin or bool(role and (board.visibility == "team" or member))
    view = edit or board.visibility == "public-read"
    return {"can_view": bool(view), "can_edit": bool(edit), "can_admin": bool(admin)}

def require_board(db, board_id, user, operation):
    board = db.get(Board, board_id)
    if not board:
        raise HTTPException(404, "Board not found")
    if not board_permissions(db, board, user)[operation]:
        raise HTTPException(403, "Board permission required")
    return board

def require_board_view(db, board_id, user):
    return require_board(db, board_id, user, "can_view")

def require_board_edit(db, board_id, user):
    return require_board(db, board_id, user, "can_edit")

def require_board_admin(db, board_id, user):
    return require_board(db, board_id, user, "can_admin")
