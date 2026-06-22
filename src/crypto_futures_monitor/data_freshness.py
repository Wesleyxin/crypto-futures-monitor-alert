from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class BarCloseDedup:
    """
    仅当「数据边界」严格推进时才允许触发推送，避免 REST 轮询对同一根已收盘 K 线 / 同一 OI 统计窗重复告警。
    边界使用交易所返回的毫秒时间戳（K 线 close time、OI hist 最新点 timestamp 等）。
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_boundary_ms: dict[tuple[str, str], int] = {}

    async def claim(self, symbol: str, rule_key: str, data_boundary_ms: int) -> bool:
        if data_boundary_ms <= 0:
            return False
        k = (symbol.upper(), rule_key)
        async with self._lock:
            prev = self._last_boundary_ms.get(k, -1)
            if data_boundary_ms <= prev:
                log.debug(
                    "跳过重复数据 %s %s boundary=%s last=%s",
                    symbol,
                    rule_key,
                    data_boundary_ms,
                    prev,
                )
                return False
            self._last_boundary_ms[k] = data_boundary_ms
        return True
