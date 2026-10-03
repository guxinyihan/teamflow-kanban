from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..auth.deps import get_current_user
from ..authorization.policy import require_team, team_role
from ..domain import team_lock
from ..models import Invitation, TeamMember, User
from ..schemas import InviteCreate, InviteAccept
from ..serialization import iso
from ..config import settings
from ..activity.service import record_event

router = APIRouter()

def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def invitation_dict(item):
    return {"id": item.id, "team_id": item.team_id, "email": item.email,
            "role": item.role, "created_at": iso(item.created_at),
            "expires_at": iso(item.expires_at), "accepted_at": iso(item.accepted_at),
            "revoked_at": iso(item.revoked_at)}

def invitation_admin(db, team_id, user, role="member"):
    roles = ("owner",) if role == "admin" else ("owner", "admin")
    require_team(db, team_id, user, roles)
    team = team_lock(db, team_id)
    require_team(db, team_id, user, roles)
    return team

@router.get("/teams/{team_id}/invitations")
def list_invitations(team_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_team(db, team_id, user, ("owner", "admin"))
    invitations = db.query(Invitation).filter_by(team_id=team_id).order_by(Invitation.id.desc()).all()
    return [invitation_dict(item) for item in invitations]

@router.post("/teams/{team_id}/invitations", status_code=201)
def create_invitation(team_id: int, data: InviteCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    team = invitation_admin(db, team_id, user, data.role)
    existing_user = db.query(User).filter(func.lower(User.email) == data.email).first()
    if existing_user and db.get(TeamMember, (team_id, existing_user.id)):
        raise HTTPException(409, "User is already a team member")
    now = datetime.now(timezone.utc)
    pending = db.query(Invitation).filter_by(team_id=team_id, email=data.email, accepted_at=None, revoked_at=None).all()
    for item in pending:
        if as_utc(item.expires_at) > now:
            raise HTTPException(409, "A pending invitation already exists; revoke it before creating another")
    token = secrets.token_urlsafe(32)
    item = Invitation(team_id=team_id, email=data.email, role=data.role,
                      token_hash=hashlib.sha256(token.encode()).hexdigest(), created_by=user.id,
                      expires_at=now + timedelta(hours=settings.INVITE_HOURS))
    db.add(item)
    db.flush()
    record_event(db, user, "member.invited", "invitation", item.id, team=team,
                 details={"email": data.email, "role": data.role})
    db.commit()
    result = invitation_dict(item)
    result.update(token=token, invitation_url=f"{settings.FRONTEND_ORIGINS[0]}/?invite={token}")
    return result

@router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.get(Invitation, invitation_id)
    if item is None:
        raise HTTPException(404, "Invitation not found")
    team = invitation_admin(db, item.team_id, user, item.role)
    item = db.get(Invitation, invitation_id)
    if item.accepted_at:
        raise HTTPException(409, "Invitation already accepted")
    item.revoked_at = datetime.now(timezone.utc)
    record_event(db, user, "invitation.revoked", "invitation", item.id, team=team)
    db.commit()
    return {"message": "Invitation revoked"}

@router.post("/invitations/accept")
def accept_invitation(data: InviteAccept, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    token_hash = hashlib.sha256(data.token.encode()).hexdigest()
    item = db.query(Invitation).filter_by(token_hash=token_hash).first()
    if item is None:
        raise HTTPException(404, "Invitation not found")
    team = team_lock(db, item.team_id)
    item = db.get(Invitation, item.id)
    now = datetime.now(timezone.utc)
    if item.accepted_at or item.revoked_at or as_utc(item.expires_at) <= now:
        raise HTTPException(410, "Invitation expired or no longer active")
    if user.email.lower() != item.email:
        raise HTTPException(403, "Invitation belongs to a different account")
    creator = db.get(User, item.created_by)
    issuer_role = team_role(db, team.id, creator) if creator else None
    if issuer_role not in (("owner",) if item.role == "admin" else ("owner", "admin")):
        raise HTTPException(410, "Invitation issuer no longer has permission")
    if db.get(TeamMember, (team.id, user.id)):
        raise HTTPException(409, "User is already a team member")
    db.add(TeamMember(team_id=team.id, user_id=user.id, role=item.role))
    item.accepted_at = now
    record_event(db, user, "member.joined", "user", user.id, team=team, details={"role": item.role})
    db.commit()
    return {"team_id": team.id, "role": item.role, "message": "Invitation accepted"}
