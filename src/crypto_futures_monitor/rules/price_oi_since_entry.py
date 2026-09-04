from __future__ import annotations

import logging

from ..models import AlertEvent, alert_now
from .base import RuleContext, RuleTarget

log = logging.getLogger(__name__)


class PriceOiSinceEntryRule:
    rule_type = "price_oi_since_watchlist_high"

    async def evaluate(self, context: RuleContext, target: RuleTarget) -> None:
        symbol = target.symbol
        try:
            oi_cur = float((await context.client.open_interest(symbol))["openInterest"])
        except Exception as exc:
            log.debug("读取当前 OI 失败 %s: %s", symbol, exc)
            oi_cur = None
        try:
            price_cur = float((await context.client.mark_price(symbol))["markPrice"])
        except Exception as exc:
            log.debug("读取当前标记价格失败 %s: %s", symbol, exc)
            price_cur = None

        price_broke, oi_broke, prev_max_price, prev_max_oi = await context.store.record_price_oi_high_water(
            symbol, price_cur, oi_cur
        )
        if not (price_broke and oi_broke and prev_max_price is not None and prev_max_oi is not None):
            return

        await context.alerts.emit(
            AlertEvent(
                symbol=symbol,
                rule_type=self.rule_type,
                triggered_at=alert_now(),
                values={
                    "price": price_cur,
                    "oi": oi_cur,
                    "prev_max_price": prev_max_price,
                    "prev_max_oi": prev_max_oi,
                    "_cooldown_sec_override": 1800,
                },
                watchlist_reasons=target.reasons,
                message="持仓量和价格同时突破加入列表以来的最高点",
                watchlist_entry_at=target.entry.entry_time,
            )
        )
