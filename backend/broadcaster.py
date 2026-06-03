"""
Global SSE broadcaster.
Any coroutine in the process can call `publish(event)` and every
connected /events client will receive it instantly.
"""
import asyncio
import logging

log = logging.getLogger("research.broadcaster")

_subscribers: list[asyncio.Queue] = []


async def publish(event: dict) -> None:
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)
    if _subscribers:
        log.debug("broadcast → %d clients: %s", len(_subscribers), event.get("type"))


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass
