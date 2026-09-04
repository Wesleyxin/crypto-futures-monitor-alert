from __future__ import annotations

from .base import AlertRule
from .price_oi_rolling_7d import PriceOiRolling7dRule
from .price_oi_since_entry import PriceOiSinceEntryRule
from .volume_spike_10m import VolumeSpike10mRule

DEFAULT_RULES: tuple[AlertRule, ...] = (
    PriceOiSinceEntryRule(),
    PriceOiRolling7dRule(),
    VolumeSpike10mRule(),
)

__all__ = [
    "AlertRule",
    "DEFAULT_RULES",
    "PriceOiRolling7dRule",
    "PriceOiSinceEntryRule",
    "VolumeSpike10mRule",
]
