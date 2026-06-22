from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta, timezone
from logging import Formatter
from typing import Optional

from .alerts import AlertManager
from .alt_monitor import poll_watchlist_alt_rules
from .binance import BinanceFuturesClient
from .coingecko import CoinGeckoMcapCache
from .dashboard import run_dashboard_server
from .data_freshness import BarCloseDedup
from .recent_buffer import RecentAlertsBuffer
from .rule_toggles import RuleToggleStore
from .settings import load_config
from .watchlist import WatchlistStore, run_watchlist_scan

log = logging.getLogger(__name__)


class _Utc8LogFormatter(Formatter):
    """日志 asctime 使用 UTC+8。"""

    _tz = timezone(timedelta(hours=8))

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(self._tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def _setup_logging() -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_Utc8LogFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(h)
    root.setLevel(logging.INFO)


def _install_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass


async def _watchlist_task(
    stop: asyncio.Event,
    client: BinanceFuturesClient,
    store: WatchlistStore,
    mcap: CoinGeckoMcapCache,
    cfg: dict,
) -> None:
    sec = int(cfg.get("watchlist", {}).get("scanIntervalSec", 300))
    while not stop.is_set():
        try:
            await run_watchlist_scan(client, store, mcap, cfg)
        except Exception:
            log.exception("观察列表扫描异常")
        try:
            await asyncio.wait_for(stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            continue


async def _alt_poll_task(
    stop: asyncio.Event,
    client: BinanceFuturesClient,
    store: WatchlistStore,
    alerts: AlertManager,
    interval_sec: float,
    dedup: BarCloseDedup,
) -> None:
    while not stop.is_set():
        try:
            await poll_watchlist_alt_rules(client, store, alerts, dedup)
        except Exception:
            log.exception("标的级规则轮询异常")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue


async def async_main(config_path: Optional[str]) -> None:
    _setup_logging()
    cfg = load_config(config_path)
    stop = asyncio.Event()
    _install_handlers(stop)

    rest = str(cfg["binance"]["restBaseUrl"])
    client = BinanceFuturesClient(rest)
    store = WatchlistStore(str(cfg.get("watchlist", {}).get("manualStorePath", ".monitor_manual_watchlist.json")))
    rule_toggles = RuleToggleStore(str(cfg.get("ui", {}).get("ruleToggleStorePath", ".monitor_rule_toggles.json")))
    cg_cfg = cfg.get("coingecko", {})
    mcap = CoinGeckoMcapCache(str(cg_cfg.get("baseUrl", "https://api.coingecko.com/api/v3")), bool(cg_cfg.get("enabled", True)))
    al_cfg = cfg.get("alert", {})
    recent = RecentAlertsBuffer(maxlen=int(cfg.get("ui", {}).get("recentAlertMax", 300)))
    alerts = AlertManager(
        int(al_cfg.get("cooldownSec", 300)),
        str(al_cfg.get("webhookUrl", "")),
        str(al_cfg.get("wecomWebhookUrl", "")),
        str(al_cfg.get("discordWebhookUrl", "")),
        recent,
        binance_client=client,
        mcap_cache=mcap,
        rule_toggle_store=rule_toggles,
    )
    dedup = BarCloseDedup()
    alt_poll_interval_sec = float(cfg.get("altPollIntervalSec", 45))

    try:
        await client.ping()
        log.info("REST 连通性检查通过 base=%s", rest)
    except Exception as e:
        log.error("REST 无法连通（请检查地址与网络）: %s", e)

    try:
        await asyncio.gather(
            _watchlist_task(stop, client, store, mcap, cfg),
            _alt_poll_task(stop, client, store, alerts, alt_poll_interval_sec, dedup),
            run_dashboard_server(
                stop,
                store,
                recent,
                cfg,
                client=client,
                mcap=mcap,
                rule_toggles=rule_toggles,
            ),
        )
    except asyncio.CancelledError:
        pass
    finally:
        stop.set()
        await alerts.aclose()
        await mcap.aclose()
        await client.aclose()


def main() -> None:
    cfg_path = None
    if len(sys.argv) > 1:
        cfg_path = sys.argv[1]
    try:
        asyncio.run(async_main(cfg_path))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
