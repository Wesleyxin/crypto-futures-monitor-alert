from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional

from .binance import BinanceFuturesClient
from .coingecko import CoinGeckoMcapCache
from .models import AlertEvent

log = logging.getLogger(__name__)


async def enrich_alert_market_snapshot(
    client: BinanceFuturesClient,
    mcap: Optional[CoinGeckoMcapCache],
    event: AlertEvent,
) -> AlertEvent:
    """在推送前合并：持仓名义价值（OI×标记价）、代币市值、持仓/市值比。"""
    vals = dict(event.values)
    sym = event.symbol.upper()
    oi_val: Optional[float] = None
    mcap_val: Optional[float] = None
    try:
        oi_r = await client.open_interest(sym)
        mp_r = await client.mark_price(sym)
        qty = float(oi_r["openInterest"])
        mark = float(mp_r["markPrice"])
        vals["open_interest_quantity"] = qty
        vals["mark_price_usdt"] = mark
        oi_val = qty * mark
        vals["open_interest_value_usdt"] = oi_val
    except Exception as e:
        log.debug("告警市场快照：OI/标记价 获取失败 %s: %s", sym, e)
        vals["open_interest_value_usdt"] = None
        vals["open_interest_quantity"] = None
        vals["mark_price_usdt"] = None

    if mcap is not None and mcap.enabled:
        try:
            mcap_val = await mcap.market_cap_usd(sym)
            vals["market_cap_usdt"] = mcap_val
        except Exception as e:
            log.debug("告警市场快照：市值 获取失败 %s: %s", sym, e)
            vals["market_cap_usdt"] = None
    else:
        vals["market_cap_usdt"] = None

    if oi_val is not None and mcap_val is not None and mcap_val > 0:
        vals["oi_value_to_mcap_ratio"] = oi_val / mcap_val
    else:
        vals["oi_value_to_mcap_ratio"] = None

    return replace(event, values=vals)
