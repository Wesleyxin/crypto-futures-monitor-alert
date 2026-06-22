from __future__ import annotations

import logging
from typing import Optional

from .alerts import AlertManager
from .binance import BinanceFuturesClient
from .data_freshness import BarCloseDedup
from .models import AlertEvent, alert_now
from .watchlist import WatchlistStore, reason_labels_for

log = logging.getLogger(__name__)


def _rolling_high(rows: list[float]) -> Optional[float]:
    if not rows:
        return None
    return max(rows)


def _latest_closed_10m_volume_comparison(rows: list[list[object]]) -> Optional[tuple[float, float, float, int]]:
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


async def poll_watchlist_alt_rules(
    client: BinanceFuturesClient,
    store: WatchlistStore,
    alerts: AlertManager,
    dedup: BarCloseDedup,
) -> None:
    snap = await store.snapshot()
    for sym, entry in snap.items():
        reasons = reason_labels_for(entry)

        try:
            oi_cur = float((await client.open_interest(sym))["openInterest"])
        except Exception as e:
            log.debug("读取当前 OI 失败 %s: %s", sym, e)
            oi_cur = None
        try:
            price_cur = float((await client.mark_price(sym))["markPrice"])
        except Exception as e:
            log.debug("读取当前标记价格失败 %s: %s", sym, e)
            price_cur = None

        price_broke, oi_broke, prev_max_price, prev_max_oi = await store.record_price_oi_high_water(sym, price_cur, oi_cur)
        if price_broke and oi_broke and prev_max_price is not None and prev_max_oi is not None:
            evt = AlertEvent(
                symbol=sym,
                rule_type="price_oi_since_watchlist_high",
                triggered_at=alert_now(),
                values={
                    "price": price_cur,
                    "oi": oi_cur,
                    "prev_max_price": prev_max_price,
                    "prev_max_oi": prev_max_oi,
                    "_cooldown_sec_override": 1800,
                },
                watchlist_reasons=reasons,
                message="持仓量和价格同时突破加入列表以来的最高点",
                watchlist_entry_at=entry.entry_time,
            )
            await alerts.emit(evt)

        try:
            kl_1h = await client.klines(sym, "1h", limit=170)
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
        except Exception as e:
            log.debug("读取 7d 价格高点失败 %s: %s", sym, e)
            price_1h = None
            price_7d_high = None
            price_1h_boundary = None

        try:
            oi_1h_hist = await client.open_interest_hist(sym, "1h", 169)
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
        except Exception as e:
            log.debug("读取 7d OI 高点失败 %s: %s", sym, e)
            oi_1h = None
            oi_7d_high = None
            oi_1h_boundary = None

        oi_7d_broke = oi_1h is not None and oi_7d_high is not None and oi_1h > oi_7d_high
        price_7d_broke = price_1h is not None and price_7d_high is not None and price_1h > price_7d_high
        rolling_7d_boundary = max(x for x in [price_1h_boundary, oi_1h_boundary] if x is not None) if (
            price_1h_boundary is not None or oi_1h_boundary is not None
        ) else None
        if oi_7d_broke and price_7d_broke and rolling_7d_boundary is not None:
            if await dedup.claim(sym, "price_oi_rolling_7d_high", rolling_7d_boundary):
                evt = AlertEvent(
                    symbol=sym,
                    rule_type="price_oi_rolling_7d_high",
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
                    watchlist_reasons=reasons,
                    message="持仓量和价格同时突破7日滚动高点",
                    watchlist_entry_at=entry.entry_time,
                )
                await alerts.emit(evt)

        try:
            kl_5m = await client.klines(sym, "5m", limit=10)
            closed_5m = kl_5m[:-1]
            ten_min_result = _latest_closed_10m_volume_comparison(closed_5m)
        except Exception as e:
            log.debug("读取 10m 成交量窗口失败 %s: %s", sym, e)
            ten_min_result = None
        if ten_min_result is not None:
            volume_chg_pct, current_volume_10m, previous_volume_10m, volume_10m_boundary = ten_min_result
            if volume_chg_pct >= 10.0 and await dedup.claim(sym, "volume_spike_10m", volume_10m_boundary):
                evt = AlertEvent(
                    symbol=sym,
                    rule_type="volume_spike_10m",
                    triggered_at=alert_now(),
                    values={
                        "interval": "10m",
                        "volume_chg_pct": volume_chg_pct,
                        "current_volume_10m": current_volume_10m,
                        "previous_volume_10m": previous_volume_10m,
                        "bar_close_ms": volume_10m_boundary,
                    },
                    watchlist_reasons=reasons,
                    message=f"10m成交量较前10m涨幅 {volume_chg_pct * 100:.2f}%",
                    watchlist_entry_at=entry.entry_time,
                )
                await alerts.emit(evt)
