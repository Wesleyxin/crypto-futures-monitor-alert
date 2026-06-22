from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from .alert_format import build_alert_lines, format_beijing_time, rule_title_cn
from .models import AlertEvent


class RecentAlertsBuffer:
    """内存环形缓冲区，供 Web 看板展示近期已发出告警（通过冷却后的实际推送）。"""

    def __init__(self, maxlen: int = 300) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = asyncio.Lock()

    async def add(self, event: AlertEvent) -> None:
        we = event.watchlist_entry_at
        row = {
            "symbol": event.symbol,
            "rule_type": event.rule_type,
            "rule_title": rule_title_cn(event.rule_type),
            "triggered_at_utc": event.triggered_at.isoformat(),
            "triggered_at_beijing": format_beijing_time(event.triggered_at),
            "watchlist_entry_at_utc": we.isoformat() if we is not None else None,
            "watchlist_entry_at_beijing": format_beijing_time(we) if we is not None else None,
            "display_lines": build_alert_lines(event),
            "values": event.values,
            "watchlist_reasons": event.watchlist_reasons,
            "message": event.message,
        }
        async with self._lock:
            self._items.append(row)

    async def list_recent(self) -> list[dict[str, Any]]:
        async with self._lock:
            return list(reversed(self._items))
