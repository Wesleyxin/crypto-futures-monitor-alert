from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

RULE_TOGGLE_DEFS = [
    {"rule_type": "price_oi_since_watchlist_high", "title": "观察列表 · 持仓量和价格同时突破入列后最高点", "group": "观察列表"},
    {"rule_type": "price_oi_rolling_7d_high", "title": "观察列表 · 持仓量和价格同时突破7日滚动高点", "group": "观察列表"},
    {"rule_type": "volume_spike_10m", "title": "观察列表 · 10m成交量涨幅超1000%", "group": "观察列表"},
]

_RULE_META = {item["rule_type"]: item for item in RULE_TOGGLE_DEFS}


class RuleToggleStore:
    def __init__(self, store_path: str) -> None:
        self._lock = asyncio.Lock()
        self._path = Path(store_path).expanduser()
        self._enabled_by_rule = self._read_enabled_map()

    def _read_enabled_map(self) -> dict[str, bool]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception as e:
            log.warning("读取规则开关失败 %s: %s", self._path, e)
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, bool] = {}
        for rule_type, enabled in raw.items():
            if isinstance(rule_type, str):
                out[rule_type] = bool(enabled)
        return out

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._enabled_by_rule, ensure_ascii=False, indent=2), encoding="utf-8")

    async def is_enabled(self, rule_type: str) -> bool:
        async with self._lock:
            return self._enabled_by_rule.get(rule_type, True)

    async def set_enabled(self, rule_type: str, enabled: bool) -> bool:
        if rule_type not in _RULE_META:
            raise ValueError("未知规则")
        async with self._lock:
            self._enabled_by_rule[rule_type] = bool(enabled)
            self._save_locked()
            return self._enabled_by_rule[rule_type]

    async def list_items(self) -> list[dict[str, object]]:
        async with self._lock:
            return [
                {
                    "rule_type": item["rule_type"],
                    "title": item["title"],
                    "group": item["group"],
                    "enabled": self._enabled_by_rule.get(item["rule_type"], True),
                }
                for item in RULE_TOGGLE_DEFS
            ]
