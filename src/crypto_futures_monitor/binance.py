from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

log = logging.getLogger(__name__)


class BinanceFuturesClient:
    """币安 U 本位 REST；baseUrl 不含尾斜杠，路径使用 /fapi/v1 与 /futures/data。"""

    def __init__(self, rest_base_url: str, timeout: float = 30.0) -> None:
        self._base = rest_base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def ping(self) -> bool:
        await self._get("/fapi/v1/ping")
        return True

    async def server_time(self) -> int:
        j = await self._get("/fapi/v1/time")
        return int(j["serverTime"])

    async def exchange_info(self) -> dict[str, Any]:
        return await self._get("/fapi/v1/exchangeInfo")

    async def open_interest(self, symbol: str) -> dict[str, Any]:
        return await self._get("/fapi/v1/openInterest", {"symbol": symbol})

    async def open_interest_hist(
        self, symbol: str, period: str, limit: int = 30, start_time: Optional[int] = None, end_time: Optional[int] = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"symbol": symbol, "period": period, "limit": limit}
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return await self._get("/futures/data/openInterestHist", params)

    async def klines(self, symbol: str, interval: str, limit: int = 500) -> list[list[Any]]:
        return await self._get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    async def mark_price(self, symbol: str) -> dict[str, Any]:
        return await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})


def futures_ws_stream_url(ws_base: str, streams: list[str]) -> str:
    base = ws_base.rstrip("/")
    q = "/".join(streams)
    if base.endswith("/ws"):
        return f"{base}/stream?streams={q}"
    return f"{base}/stream?streams={q}"


async def ws_json_messages(ws_url: str, stop: asyncio.Event) -> AsyncIterator[dict[str, Any]]:
    import websockets

    backoff = 1.0
    while not stop.is_set():
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=60) as ws:
                backoff = 1.0
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=120)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, dict):
                        yield msg
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if stop.is_set():
                break
            log.warning("WebSocket 断开，%s 秒后重连: %s", backoff, e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
