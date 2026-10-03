"""Small response projections avoid nested board/team/auth record disclosure."""
from .authorization.policy import board_permissions, team_role
from .models import TeamMember, BoardMember, User

def iso(value):
    if value is None:
        return None
    from datetime import timezone
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()

def user_dict(user, include_email=True):
    result = {"id": user.id, "username": user.username, "full_name": user.full_name}
    if include_email:
        result["email"] = user.email
    return result

def team_dict(db, team, user):
    members = db.query(TeamMember).filter_by(team_id=team.id).order_by(TeamMember.joined_at, TeamMember.user_id).all()
    return {"id": team.id, "name": team.name, "description": team.description,
            "owner_id": team.owner_id, "created_by_id": team.created_by_id,
            "role": team_role(db, team.id, user), "created_at": iso(team.created_at),
            "members": [{"user": user_dict(db.get(User, member.user_id)), "role": member.role} for member in members]}

def board_dict(db, board, user):
    result = {"id": board.id, "name": board.name, "description": board.description,
              "team_id": board.team_id, "visibility": board.visibility,
              "revision": board.revision, "created_by_id": board.created_by_id,
              "created_at": iso(board.created_at)}
    result.update(board_permissions(db, board, user))
    memberships = db.query(BoardMember).filter_by(board_id=board.id).all()
    result["members"] = [{"user": user_dict(db.get(User, member.user_id), False), "role": member.role} for member in memberships]
    return result

def label_dict(label):
    return {"id": label.id, "board_id": label.board_id, "name": label.name, "color": label.color}

def attachment_dict(item):
    return {"id": item.id, "task_id": item.task_id, "user_id": item.user_id,
            "uploader_id": item.user_id, "filename": item.original_name or item.filename,
            "original_name": item.original_name or item.filename, "size": item.size,
            "content_type": item.content_type, "created_at": iso(item.created_at),
            "url": f"/api/attachments/{item.id}/download"}

def comment_dict(item):
    return {"id": item.id, "task_id": item.task_id, "content": item.content,
            "user_id": item.user_id, "user_name": item.user_name,
            "created_at": iso(item.created_at), "updated_at": iso(item.updated_at)}

def task_dict(task):
    return {"id": task.id, "board_id": task.board_id, "column_id": task.column_id,
            "title": task.title, "description": task.description or "", "priority": task.priority,
            "position": task.position, "status": task.status, "creator_id": task.creator_id,
            "assignee_id": task.assignee_id, "assignee": user_dict(task.assignee, False) if task.assignee else None,
            "assigned_to": [user_dict(task.assignee, False)] if task.assignee else [],
            "version": task.version, "is_archived": task.is_archived, "archived_at": iso(task.archived_at),
            "due_date": iso(task.due_date), "created_at": iso(task.created_at), "updated_at": iso(task.updated_at),
            "labels": [label_dict(item) for item in task.labels],
            "comments": [comment_dict(item) for item in task.comments],
            "attachments": [attachment_dict(item) for item in task.attachments],
            "checklist": task.checklist or []}

def activity_dict(item):
    return {"id": item.id, "actor_id": item.actor_id, "actor_name": item.actor_name,
            "action": item.action, "entity_type": item.entity_type, "entity_id": item.entity_id,
            "created_at": iso(item.created_at), "details": item.details}

def column_dict(column, active_count=0):
    return {"id": column.id, "board_id": column.board_id, "name": column.name,
            "position": column.position, "wip_limit": column.wip_limit, "active_count": active_count}
