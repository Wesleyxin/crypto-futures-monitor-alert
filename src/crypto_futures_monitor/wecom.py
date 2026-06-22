from __future__ import annotations

import logging
from typing import Any

import httpx

from .alert_format import build_wecom_markdown
from .models import AlertEvent

log = logging.getLogger(__name__)


def _truncate_bytes(s: str, max_bytes: int) -> str:
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s
    out = []
    n = 0
    for ch in s:
        c = ch.encode("utf-8")
        if n + len(c) > max_bytes - 20:
            break
        out.append(ch)
        n += len(c)
    return "".join(out) + "\n…(已截断)"


async def send_wecom_robot(client: httpx.AsyncClient, webhook_url: str, event: AlertEvent) -> None:
    """企业微信群机器人 Webhook（POST JSON，msgtype=markdown，中文排版 + 北京时间）。"""
    url = webhook_url.strip()
    if not url:
        return
    content = _truncate_bytes(build_wecom_markdown(event), 3800)
    body: dict[str, Any] = {"msgtype": "markdown", "markdown": {"content": content}}
    r = await client.post(url, json=body)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        data = {}
    if isinstance(data, dict) and int(data.get("errcode", 0)) != 0:
        log.error("企业微信返回错误: %s", data)
