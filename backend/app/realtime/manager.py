"""Single-worker board channels; events invalidate snapshots after SQL commit."""
import asyncio
from dataclasses import dataclass, field
import time
from .. import database
from ..models import Board, User
from ..authorization.policy import board_permissions

@dataclass(eq=False)
class Subscription:
    board_id: int
    user_id: int
    expires_at: float
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=64))

class BoardChannels:
    def __init__(self):
        self.channels: dict[int, set[Subscription]] = {}

    def join(self, board_id, user_id, expires_at):
        subscription = Subscription(board_id, user_id, expires_at)
        self.channels.setdefault(board_id, set()).add(subscription)
        return subscription

    def leave(self, subscription):
        subscribers = self.channels.get(subscription.board_id, set())
        subscribers.discard(subscription)
        if not subscribers:
            self.channels.pop(subscription.board_id, None)

    def eligible(self, subscription):
        if subscription.expires_at <= time.time():
            return False
        with database.SessionLocal() as db:
            user = db.get(User, subscription.user_id)
            board = db.get(Board, subscription.board_id)
            return bool(user and board and board_permissions(db, board, user)["can_view"])

    async def publish(self, message):
        for subscription in tuple(self.channels.get(message["board_id"], ())):
            try:
                eligible = self.eligible(subscription)
            except Exception:
                import logging
                logging.getLogger("teamflow").error("Board subscription could not be revalidated")
                eligible = False
            if not eligible:
                self._enqueue(subscription, {"type": "close"})
                continue
            self._enqueue(subscription, message)

    def _enqueue(self, subscription, message):
        try:
            subscription.queue.put_nowait(message)
        except asyncio.QueueFull:
            # Slow clients reconnect and refetch; never silently keep stale state.
            while not subscription.queue.empty():
                subscription.queue.get_nowait()
            subscription.queue.put_nowait({"type": "close"})

manager = BoardChannels()
