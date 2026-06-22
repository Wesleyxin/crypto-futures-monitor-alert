from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


def base_asset_from_symbol(symbol: str) -> str:
    s = symbol.upper().removesuffix("USDT")
    for prefix in ("1000000", "100000", "10000", "1000"):
        if s.startswith(prefix) and len(s) > len(prefix):
            return s[len(prefix) :]
    return s


class CoinGeckoMcapCache:
    """从 /coins/markets 拉取分页，建立 base 符号（大写）到市值(USD) 的近似索引。"""

    def __init__(self, base_url: str, enabled: bool) -> None:
        self._base = base_url.rstrip("/")
        self._enabled = enabled
        self._client = httpx.AsyncClient(base_url=self._base, timeout=45.0)
        self._symbol_to_mcap: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def aclose(self) -> None:
        await self._client.aclose()

    async def refresh(self, pages: int = 8) -> None:
        if not self._enabled:
            return
        mapping: dict[str, float] = {}
        try:
            for page in range(1, pages + 1):
                r = await self._client.get(
                    "/coins/markets",
                    params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": page},
                )
                if r.status_code == 429:
                    log.warning("CoinGecko 限流，跳过本轮市值缓存刷新")
                    return
                r.raise_for_status()
                rows: list[dict[str, Any]] = r.json()
                if not rows:
                    break
                for row in rows:
                    sym = str(row.get("symbol", "")).upper()
                    mcap = row.get("market_cap")
                    if sym and isinstance(mcap, (int, float)) and mcap > 0:
                        mapping[sym] = max(mapping.get(sym, 0.0), float(mcap))
                await asyncio.sleep(0.35)
        except Exception as e:
            log.warning("CoinGecko 刷新失败: %s", e)
            return
        async with self._lock:
            self._symbol_to_mcap = mapping
        log.info("CoinGecko 市值缓存已更新，条目数=%s", len(mapping))

    async def market_cap_usd(self, symbol: str) -> Optional[float]:
        if not self._enabled:
            return None
        base = base_asset_from_symbol(symbol)
        async with self._lock:
            return self._symbol_to_mcap.get(base)
