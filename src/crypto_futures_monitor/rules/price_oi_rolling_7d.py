from __future__ import annotations

import logging
from typing import Optional

from ..models import AlertEvent, alert_now
from .base import RuleContext, RuleTarget

log = logging.getLogger(__name__)


def _rolling_high(rows: list[float]) -> Optional[float]:
    if not rows:
        return None
    return max(rows)


class PriceOiRolling7dRule:
    rule_type = "price_oi_rolling_7d_high"

    async def evaluate(self, context: RuleContext, target: RuleTarget) -> None:
        symbol = target.symbol
        try:
            kl_1h = await context.client.klines(symbol, "1h", limit=170)
            closed_1h = kl_1h[:-1]
            if len(closed_1h) >= 169:
                latest_price_row = closed_1h[-1]
                prev_price_rows = closed_1h[-169:-1]
                price_1h = float(latest_price_row[4])
                price_7d_high = _rolling_high([float(row[4]) for row in prev_price_rows])
                price_1h_boundary = int(latest_price_row[6])
            else:
                price_1h = None
                price_7d_high = None
                price_1h_boundary = None
        except Exception as exc:
            log.debug("读取 7d 价格高点失败 %s: %s", symbol, exc)
            price_1h = None
            price_7d_high = None
            price_1h_boundary = None

        try:
            oi_1h_hist = await context.client.open_interest_hist(symbol, "1h", 169)
            ordered_oi_1h = sorted(oi_1h_hist, key=lambda row: int(row.get("timestamp", 0)))
            if len(ordered_oi_1h) >= 169:
                latest_oi_row = ordered_oi_1h[-1]
                prev_oi_rows = ordered_oi_1h[-169:-1]
                oi_1h = float(latest_oi_row["sumOpenInterest"])
                oi_7d_high = _rolling_high([float(row["sumOpenInterest"]) for row in prev_oi_rows])
                oi_1h_boundary = int(latest_oi_row.get("timestamp", 0))
            else:
                oi_1h = None
                oi_7d_high = None
                oi_1h_boundary = None
        except Exception as exc:
            log.debug("读取 7d OI 高点失败 %s: %s", symbol, exc)
            oi_1h = None
            oi_7d_high = None
            oi_1h_boundary = None

        oi_broke = oi_1h is not None and oi_7d_high is not None and oi_1h > oi_7d_high
        price_broke = price_1h is not None and price_7d_high is not None and price_1h > price_7d_high
        boundaries = [value for value in (price_1h_boundary, oi_1h_boundary) if value is not None]
        boundary = max(boundaries) if boundaries else None
        if not (oi_broke and price_broke and boundary is not None):
            return
        if not await context.dedup.claim(symbol, self.rule_type, boundary):
            return

        await context.alerts.emit(
            AlertEvent(
                symbol=symbol,
                rule_type=self.rule_type,
                triggered_at=alert_now(),
                values={
                    "interval": "7d",
                    "price": price_1h,
                    "oi": oi_1h,
                    "prev_price_7d_high": price_7d_high,
                    "prev_oi_7d_high": oi_7d_high,
                    "bar_close_ms": price_1h_boundary,
                    "oi_hist_boundary_ms": oi_1h_boundary,
                },
                watchlist_reasons=target.reasons,
                message="持仓量和价格同时突破7日滚动高点",
                watchlist_entry_at=target.entry.entry_time,
            )
        )
