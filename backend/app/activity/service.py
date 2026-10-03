from sqlalchemy import event
from ..models import ActivityEvent

@event.listens_for(ActivityEvent, "before_update")
@event.listens_for(ActivityEvent, "before_delete")
def immutable_activity(*_):
    raise ValueError("Activity records are append-only")

def record_event(db, actor, action, entity_type, entity_id, board=None, team=None, details=None):
    item = ActivityEvent(team_id=board.team_id if board else team.id,
                         board_id=board.id if board else None,
                         actor_id=actor.id, actor_name=actor.full_name or actor.username,
                         action=action, entity_type=entity_type, entity_id=entity_id,
                         details=details or {})
    db.add(item)
    return item

async def commit_board(db, board, user, action, entity_type, entity_id, details=None):
    item = record_event(db, user, action, entity_type, entity_id, board=board, details=details)
    db.flush()
    event_type = {"comment_added": "comment.created"}.get(action, action.replace("_", ".", 1))
    message = {"type": event_type, "board_id": board.id, "revision": board.revision,
               "activity_id": item.id, "entity_type": entity_type, "entity_id": entity_id}
    db.commit()
    from ..realtime.manager import manager
    try:
        await manager.publish(message)
    except Exception:
        # The SQL mutation already succeeded. Reporting a failed upload here
        # would invite a retry and could delete its now-committed private bytes.
        import logging
        logging.getLogger("teamflow").error("Committed board change could not be broadcast")
    return message["revision"]
