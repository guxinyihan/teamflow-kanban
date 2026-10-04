import asyncio
import time
import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from .. import database
from ..models import User
from ..auth.utils import verify_token
from ..authorization.policy import require_board_view
from ..config import settings
from .manager import manager

router = APIRouter()

@router.websocket("/boards/{board_id}/ws")
async def board_socket(websocket: WebSocket, board_id: int):
    origin = websocket.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.FRONTEND_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    subscription = None
    receiver = None
    delivery = None
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        token = first.get("token") if isinstance(first, dict) else None
        payload = verify_token(token) if isinstance(token, str) and len(token) <= 4096 else None
        if not payload:
            await websocket.close(code=1008)
            return
        with database.SessionLocal() as db:
            user = db.get(User, int(payload["sub"]))
            if user is None:
                await websocket.close(code=1008)
                return
            board = require_board_view(db, board_id, user)
            subscription = manager.join(board_id, user.id, payload["exp"])
            revision = board.revision
        await websocket.send_json({"type": "ready", "board_id": board_id, "revision": revision})
        heartbeat = time.monotonic()
        receiver = asyncio.create_task(websocket.receive())
        delivery = asyncio.create_task(subscription.queue.get())
        while True:
            done, _ = await asyncio.wait((receiver, delivery), timeout=2, return_when=asyncio.FIRST_COMPLETED)
            if not manager.eligible(subscription):
                await websocket.close(code=1008)
                break
            if receiver in done:
                frame = receiver.result()
                if frame["type"] == "websocket.disconnect":
                    break
                receiver = asyncio.create_task(websocket.receive())
            if delivery in done:
                message = delivery.result()
                if message["type"] == "close":
                    await websocket.close(code=1008)
                    break
                await websocket.send_json(message)
                delivery = asyncio.create_task(subscription.queue.get())
            if time.monotonic() - heartbeat >= 10:
                await websocket.send_json({"type": "ping", "board_id": board_id})
                heartbeat = time.monotonic()
    except (WebSocketDisconnect, HTTPException, asyncio.TimeoutError, ValueError):
        try:
            await websocket.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if subscription:
            manager.leave(subscription)
        for task in (receiver, delivery):
            if task:
                task.cancel()
        pending = [task for task in (receiver, delivery) if task]
        if pending:
            # Session/shutdown cancellation must not interrupt draining the
            # child tasks or replace the parent scope's cancellation exception.
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*pending, return_exceptions=True)
