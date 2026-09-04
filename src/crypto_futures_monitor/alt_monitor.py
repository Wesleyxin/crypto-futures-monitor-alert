from __future__ import annotations

import logging
from typing import Sequence

from .alerts import AlertManager
from .binance import BinanceFuturesClient
from .data_freshness import BarCloseDedup
from .rules import DEFAULT_RULES, AlertRule
from .rules.base import RuleContext, RuleTarget
from .watchlist import WatchlistStore, reason_labels_for

log = logging.getLogger(__name__)


async def poll_watchlist_alt_rules(
    client: BinanceFuturesClient,
    store: WatchlistStore,
    alerts: AlertManager,
    dedup: BarCloseDedup,
    rules: Sequence[AlertRule] = DEFAULT_RULES,
) -> None:
    """遍历观察列表，并由独立规则模块依次评估每个标的。"""
    context = RuleContext(client=client, store=store, alerts=alerts, dedup=dedup)
    snap = await store.snapshot()
    for symbol, entry in snap.items():
        target = RuleTarget(symbol=symbol, entry=entry, reasons=reason_labels_for(entry))
        for rule in rules:
            try:
                await rule.evaluate(context, target)
            except Exception:
                log.exception("规则执行异常 rule=%s symbol=%s", rule.rule_type, symbol)
