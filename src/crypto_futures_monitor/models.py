from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

# 告警展示与记录时间（UTC+8）
ALERT_TZ = timezone(timedelta(hours=8))


class WatchlistReason(str, Enum):
    MANUAL = "manual"
    OI_7D_TOP = "oi_7d_top"
    OI_1D_UP = "oi_1d_up"
    PRICE_1D_UP = "price_1d_up"
    OI_1D_DOWN = "oi_1d_down"


@dataclass
class WatchlistEntry:
    symbol: str
    entry_time: datetime
    reasons: set[WatchlistReason] = field(default_factory=set)
    rank_oi7d: Optional[int] = None
    entry_price_usdt: Optional[float] = None
    max_oi_since_entry: Optional[float] = None
    max_price_since_entry: Optional[float] = None


@dataclass
class AlertEvent:
    symbol: str
    rule_type: str
    triggered_at: datetime
    values: dict
    watchlist_reasons: list[str]
    message: str
    #: 首次进入观察列表的时间（UTC，与 WatchlistEntry.entry_time 同源）；大盘等非观察列表告警为 None
    watchlist_entry_at: Optional[datetime] = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def alert_now() -> datetime:
    """告警事件时间戳，固定为 UTC+8（东八区）。"""
    return datetime.now(ALERT_TZ)
