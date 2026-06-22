from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import httpx

from .alert_enrich import enrich_alert_market_snapshot
from .alert_format import build_generic_webhook_payload, build_log_line_cn
from .discord import send_discord_webhook
from .models import AlertEvent

if TYPE_CHECKING:
    from .binance import BinanceFuturesClient
    from .coingecko import CoinGeckoMcapCache
    from .rule_toggles import RuleToggleStore
from .recent_buffer import RecentAlertsBuffer
from .wecom import send_wecom_robot

log = logging.getLogger(__name__)


class AlertManager:
    def __init__(
        self,
        cooldown_sec: int,
        webhook_url: str = "",
        wecom_webhook_url: str = "",
        discord_webhook_url: str = "",
        recent: Optional[RecentAlertsBuffer] = None,
        binance_client: Optional["BinanceFuturesClient"] = None,
        mcap_cache: Optional["CoinGeckoMcapCache"] = None,
        rule_toggle_store: Optional["RuleToggleStore"] = None,
    ) -> None:
        self._cooldown = max(0, int(cooldown_sec))
        self._webhook = (webhook_url or "").strip()
        self._wecom = (wecom_webhook_url or "").strip()
        self._discord = (discord_webhook_url or "").strip()
        self._recent = recent
        self._binance = binance_client
        self._mcap = mcap_cache
        self._rule_toggles = rule_toggle_store
        self._last: dict[tuple[str, str], float] = {}
        self._last_daily: dict[tuple[str, str], str] = {}
        self._emit_count_daily: dict[tuple[str, str], int] = {}
        self._client: Optional[httpx.AsyncClient] = None
        if self._webhook or self._wecom or self._discord:
            self._client = httpx.AsyncClient(timeout=15.0)

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()

    def should_emit(self, event: AlertEvent) -> bool:
        symbol, rule_type = event.symbol, event.rule_type
        vals = event.values or {}
        try:
            cooldown_sec = max(0, int(vals.get("_cooldown_sec_override", self._cooldown)))
        except (TypeError, ValueError):
            cooldown_sec = self._cooldown
        if bool(vals.get("_once_per_day")):
            key = (symbol, rule_type)
            day_key = self._day_key(event.triggered_at)
            last_day = self._last_daily.get(key)
            if last_day == day_key:
                log.debug("按日去重跳过 %s %s", symbol, rule_type)
                return False
            self._last_daily[key] = day_key
        if bool(vals.get("_skip_cooldown")):
            return True
        if cooldown_sec <= 0:
            return True
        key = (symbol, rule_type)
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and now - last < cooldown_sec:
            log.debug("冷却跳过 %s %s", symbol, rule_type)
            return False
        self._last[key] = now
        return True

    @staticmethod
    def _day_key(ts: datetime) -> str:
        return ts.date().isoformat()

    def _attach_daily_emit_stats(self, event: AlertEvent) -> AlertEvent:
        day_key = self._day_key(event.triggered_at)
        count_key = (event.symbol, day_key)
        count = self._emit_count_daily.get(count_key, 0) + 1
        self._emit_count_daily[count_key] = count
        vals = dict(event.values or {})
        vals["push_count_today"] = count
        vals["is_first_push_today"] = count == 1
        return replace(event, values=vals)

    async def emit(self, event: AlertEvent) -> None:
        if self._rule_toggles is not None and not await self._rule_toggles.is_enabled(event.rule_type):
            return
        if not self.should_emit(event):
            return
        event = self._attach_daily_emit_stats(event)
        if self._binance is not None:
            event = await enrich_alert_market_snapshot(self._binance, self._mcap, event)
        log.warning("ALERT %s", build_log_line_cn(event))
        if self._recent is not None:
            await self._recent.add(event)
        if self._client and self._webhook:
            try:
                body = json.dumps(build_generic_webhook_payload(event), ensure_ascii=False)
                await self._client.post(
                    self._webhook, content=body.encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"}
                )
            except Exception as e:
                log.error("通用 Webhook 推送失败: %s", e)
        if self._client and self._wecom:
            try:
                await send_wecom_robot(self._client, self._wecom, event)
            except Exception as e:
                log.error("企业微信推送失败: %s", e)
        if self._client and self._discord:
            try:
                await send_discord_webhook(self._client, self._discord, event)
            except Exception as e:
                log.error("Discord 推送失败: %s", e)
