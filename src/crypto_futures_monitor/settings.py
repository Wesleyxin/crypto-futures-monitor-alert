from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union

import yaml


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_config_path(path: Optional[Union[str, Path]]) -> Path:
    if path is not None:
        p = Path(path).expanduser()
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"配置文件不存在: {p}")
    env = os.environ.get("MONITOR_CONFIG")
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f"MONITOR_CONFIG 指向的文件不存在: {p}")
    here = Path(__file__).resolve()
    candidates = [Path.cwd() / "config.yaml", here.parents[2] / "config.yaml"]
    for p in candidates:
        if p.is_file():
            return p.resolve()
    raise FileNotFoundError(
        "找不到 config.yaml。请：在项目根目录执行；或设置环境变量 MONITOR_CONFIG=/绝对路径/config.yaml；"
        "或执行 python -m crypto_futures_monitor /绝对路径/config.yaml"
    )


def load_config(path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    cfg_path = _resolve_config_path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    defaults: dict[str, Any] = {
        "exchange": "binance",
        "marketType": "usdt-m",
        "binance": {
            "restBaseUrl": "http://101.32.128.4:8090",
        },
        "watchlist": {
            "oi7d": {"topN": 10},
            "oi1dUp": {"minPct": 0.30},
            "price1dUp": {"minPct": 0.30},
            "oi1dDown": {"maxPct": -0.50},
            "retainDays": 10,
            "scanIntervalSec": 300,
            "manualStorePath": ".monitor_manual_watchlist.json",
        },
        "alert": {"cooldownSec": 300, "webhookUrl": "", "wecomWebhookUrl": "", "discordWebhookUrl": ""},
        "ui": {
            "enabled": False,
            "host": "0.0.0.0",
            "port": 8767,
            "authToken": "",
            "recentAlertMax": 300,
            "ruleToggleStorePath": ".monitor_rule_toggles.json",
        },
        "time": {"standard": "UTC"},
        "coingecko": {
            "enabled": True,
            "baseUrl": "https://api.coingecko.com/api/v3",
        },
        "altPollIntervalSec": 45,
    }
    return _deep_merge(defaults, raw)
