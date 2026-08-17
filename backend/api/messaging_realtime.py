from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Subscription:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]
    audience: str
    actor_id: str
    organization_id: str
    channels: frozenset[str]


class RealtimeHub:
    """Bus en memoria. REST sigue siendo la fuente de verdad y el fallback.

    Es deliberadamente intercambiable: un despliegue con varios workers puede
    sustituir este bus por Redis sin cambiar el contrato WebSocket.
    """

    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()

    def subscribe(
        self, *, audience: str, actor_id: str, organization_id: str = "",
        channels: set[str] | None = None,
    ) -> Subscription:
        item = Subscription(
            loop=asyncio.get_running_loop(), queue=asyncio.Queue(maxsize=100),
            audience=audience, actor_id=actor_id, organization_id=organization_id,
            channels=frozenset(channels or set()),
        )
        self._subscriptions.add(item)
        return item

    def unsubscribe(self, item: Subscription) -> None:
        self._subscriptions.discard(item)

    def publish(
        self, event: dict[str, Any], *, organization_id: str = "",
        channel: str = "", staff_ids: set[str] | None = None,
    ) -> None:
        for subscription in tuple(self._subscriptions):
            allowed = False
            if subscription.audience == "client":
                allowed = bool(organization_id and subscription.organization_id == organization_id)
            elif staff_ids is not None:
                allowed = subscription.actor_id in staff_ids
            else:
                allowed = not channel or channel in subscription.channels
            if not allowed:
                continue

            def enqueue(target=subscription, payload=dict(event)) -> None:
                if target.queue.full():
                    try:
                        target.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                target.queue.put_nowait(payload)

            subscription.loop.call_soon_threadsafe(enqueue)


hub = RealtimeHub()
