from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..alerts import AlertManager
from ..binance import BinanceFuturesClient
from ..data_freshness import BarCloseDedup
from ..models import WatchlistEntry
from ..watchlist import WatchlistStore


@dataclass(frozen=True)
class RuleContext:
    client: BinanceFuturesClient
    store: WatchlistStore
    alerts: AlertManager
    dedup: BarCloseDedup


@dataclass(frozen=True)
class RuleTarget:
    symbol: str
    entry: WatchlistEntry
    reasons: list[str]


class AlertRule(Protocol):
    rule_type: str

    async def evaluate(self, context: RuleContext, target: RuleTarget) -> None:
        ...
