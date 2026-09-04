from __future__ import annotations

import logging
from typing import Optional

from ..models import AlertEvent, alert_now
from .base import RuleContext, RuleTarget

log = logging.getLogger(__name__)


def latest_closed_10m_volume_comparison(
    rows: list[list[object]],
) -> Optional[tuple[float, float, float, int]]:
    """
    用已收盘 5m K 线严格合成 10m K 线，并比较「最新已收盘 10m」与「前一根已收盘 10m」。
    返回 (涨幅, 最新10m成交量, 前一根10m成交量, 最新10m收盘毫秒)。
    """
    if len(rows) < 4:
        return None

    bars_10m: list[tuple[float, int]] = []
    for idx in range(len(rows) - 1):
        first = rows[idx]
        second = rows[idx + 1]
        try:
            first_open_ms = int(first[0])
            second_open_ms = int(second[0])
            second_close_ms = int(second[6])
            if first_open_ms % 600000 != 0:
                continue
            if second_open_ms - first_open_ms != 300000:
                continue
            volume_10m = float(first[5]) + float(second[5])
        except (TypeError, ValueError, IndexError):
            continue
        bars_10m.append((volume_10m, second_close_ms))

    if len(bars_10m) < 2:
        return None

    previous_volume, _ = bars_10m[-2]
    current_volume, current_boundary_ms = bars_10m[-1]
    if previous_volume <= 1e-12:
        return None
    pct = (current_volume - previous_volume) / previous_volume
    return pct, current_volume, previous_volume, current_boundary_ms


class VolumeSpike10mRule:
    rule_type = "volume_spike_10m"

    async def evaluate(self, context: RuleContext, target: RuleTarget) -> None:
        symbol = target.symbol
        try:
            kl_5m = await context.client.klines(symbol, "5m", limit=10)
            result = latest_closed_10m_volume_comparison(kl_5m[:-1])
        except Exception as exc:
            log.debug("读取 10m 成交量窗口失败 %s: %s", symbol, exc)
            result = None
        if result is None:
            return

        volume_chg_pct, current_volume_10m, previous_volume_10m, boundary = result
        if volume_chg_pct < 10.0:
            return
        if not await context.dedup.claim(symbol, self.rule_type, boundary):
            return

        await context.alerts.emit(
            AlertEvent(
                symbol=symbol,
                rule_type=self.rule_type,
                triggered_at=alert_now(),
                values={
                    "interval": "10m",
                    "volume_chg_pct": volume_chg_pct,
                    "current_volume_10m": current_volume_10m,
                    "previous_volume_10m": previous_volume_10m,
                    "bar_close_ms": boundary,
                },
                watchlist_reasons=target.reasons,
                message=f"10m成交量较前10m涨幅 {volume_chg_pct * 100:.2f}%",
                watchlist_entry_at=target.entry.entry_time,
            )
        )
