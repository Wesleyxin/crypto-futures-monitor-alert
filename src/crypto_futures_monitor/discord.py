from __future__ import annotations

import logging
from typing import Any

import httpx

from .alert_format import build_discord_embed
from .models import AlertEvent

log = logging.getLogger(__name__)


async def send_discord_webhook(client: httpx.AsyncClient, webhook_url: str, event: AlertEvent) -> None:
    url = webhook_url.strip()
    if not url:
        return
    embed = build_discord_embed(event)
    body: dict[str, Any] = {
        "username": "观察列表告警",
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }
    r = await client.post(url, json=body)
    r.raise_for_status()
