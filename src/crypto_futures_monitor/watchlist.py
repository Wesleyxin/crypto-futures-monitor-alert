from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from .binance import BinanceFuturesClient
from .coingecko import CoinGeckoMcapCache
from .models import WatchlistEntry, WatchlistReason, utc_now

log = logging.getLogger(__name__)

_VALID_SYMBOL_RE = re.compile(r"^[A-Z0-9]+USDT$")


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _read_manual_symbols(path: Path) -> set[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except Exception as e:
        log.warning("读取手动观察列表失败 %s: %s", path, e)
        return set()
    rows = raw.get("symbols", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return set()
    return {sym for sym in (_normalize_symbol(x) for x in rows) if _VALID_SYMBOL_RE.fullmatch(sym)}


def _metric_pct(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or abs(prev) <= 1e-12:
        return None
    return (cur - prev) / abs(prev)


def _max_or_value(current: Optional[float], candidate: Optional[float]) -> Optional[float]:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max(current, candidate)


class WatchlistStore:
    def __init__(self, manual_store_path: str) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[str, WatchlistEntry] = {}
        self._manual_path = Path(manual_store_path).expanduser()
        self._manual_symbols: set[str] = _read_manual_symbols(self._manual_path)

    async def snapshot(self) -> dict[str, WatchlistEntry]:
        async with self._lock:
            return {k: replace(v) for k, v in self._entries.items()}

    async def list_manual_symbols(self) -> list[str]:
        async with self._lock:
            return sorted(self._manual_symbols)

    async def add_manual_symbol(self, symbol: str) -> str:
        sym = _normalize_symbol(symbol)
        if not _VALID_SYMBOL_RE.fullmatch(sym):
            raise ValueError("仅支持 U 本位合约交易对，格式示例：DOGEUSDT")
        now = utc_now()
        async with self._lock:
            if sym in self._entries:
                raise ValueError("该代币已在观察列表中，无需重复添加")
            self._manual_symbols.add(sym)
            prev = self._entries.get(sym)
            reasons = set(prev.reasons) if prev is not None else set()
            reasons.add(WatchlistReason.MANUAL)
            self._entries[sym] = WatchlistEntry(
                symbol=sym,
                entry_time=prev.entry_time if prev is not None else now,
                reasons=reasons,
                rank_oi7d=prev.rank_oi7d if prev is not None else None,
                entry_price_usdt=prev.entry_price_usdt if prev is not None else None,
                max_oi_since_entry=prev.max_oi_since_entry if prev is not None else None,
                max_price_since_entry=prev.max_price_since_entry if prev is not None else None,
            )
            self._save_manual_symbols_locked()
        return sym

    async def remove_manual_symbol(self, symbol: str) -> bool:
        sym = _normalize_symbol(symbol)
        async with self._lock:
            existed = sym in self._manual_symbols
            self._manual_symbols.discard(sym)
            prev = self._entries.get(sym)
            if prev is not None:
                reasons = set(prev.reasons)
                reasons.discard(WatchlistReason.MANUAL)
                if reasons:
                    self._entries[sym] = replace(prev, reasons=reasons)
                else:
                    self._entries.pop(sym, None)
            self._save_manual_symbols_locked()
            return existed

    async def reconcile(self, auto_rows: dict[str, dict[str, Any]], retain_days: int) -> None:
        now = utc_now()
        keep_window = timedelta(days=max(0, int(retain_days)))
        async with self._lock:
            new_entries: dict[str, WatchlistEntry] = {}
            all_symbols = set(self._entries) | set(auto_rows) | set(self._manual_symbols)
            for sym in sorted(all_symbols):
                prev = self._entries.get(sym)
                row = auto_rows.get(sym, {})
                reasons = set(row.get("reasons", set()))
                if sym in self._manual_symbols:
                    reasons.add(WatchlistReason.MANUAL)
                in_retain_window = prev is not None and now - prev.entry_time < keep_window
                if in_retain_window:
                    reasons = set(prev.reasons)
                if not reasons:
                    if prev is None or now - prev.entry_time >= keep_window:
                        continue
                entry_price_usdt = (
                    prev.entry_price_usdt if prev is not None and prev.entry_price_usdt is not None else row.get("entry_price_usdt")
                )
                new_entries[sym] = WatchlistEntry(
                    symbol=sym,
                    entry_time=prev.entry_time if prev is not None else now,
                    reasons=reasons,
                    rank_oi7d=prev.rank_oi7d if in_retain_window and prev is not None else row.get("rank_oi7d"),
                    entry_price_usdt=entry_price_usdt,
                    max_oi_since_entry=_max_or_value(
                        prev.max_oi_since_entry if prev is not None else None, row.get("entry_oi_qty")
                    ),
                    max_price_since_entry=_max_or_value(
                        prev.max_price_since_entry if prev is not None else None, entry_price_usdt
                    ),
                )
            self._entries = new_entries

    async def record_price_oi_high_water(
        self, symbol: str, price: Optional[float], oi: Optional[float]
    ) -> tuple[bool, bool, Optional[float], Optional[float]]:
        """原子更新价格/OI 高点，返回 (价格是否突破, OI 是否突破, 旧价格高点, 旧OI高点)。"""
        async with self._lock:
            e = self._entries.get(symbol)
            if e is None:
                return False, False, None, None
            prev_price = e.max_price_since_entry
            prev_oi = e.max_oi_since_entry
            price_broke = price is not None and prev_price is not None and price > prev_price
            oi_broke = oi is not None and prev_oi is not None and oi > prev_oi

            updates: dict[str, float] = {}
            if price is not None and (prev_price is None or price > prev_price):
                updates["max_price_since_entry"] = price
            if oi is not None and (prev_oi is None or oi > prev_oi):
                updates["max_oi_since_entry"] = oi
            if updates:
                self._entries[symbol] = replace(e, **updates)
            return price_broke, oi_broke, prev_price, prev_oi

    async def set_entry_price_if_missing(self, symbol: str, price: float) -> None:
        async with self._lock:
            e = self._entries.get(symbol)
            if e is None:
                return
            updates: dict[str, float] = {}
            if e.entry_price_usdt is None:
                updates["entry_price_usdt"] = price
            if e.max_price_since_entry is None or price > e.max_price_since_entry:
                updates["max_price_since_entry"] = price
            if not updates:
                return
            self._entries[symbol] = replace(e, **updates)

    async def set_entry_oi_if_missing(self, symbol: str, oi: float) -> None:
        async with self._lock:
            e = self._entries.get(symbol)
            if e is None:
                return
            if e.max_oi_since_entry is not None and oi <= e.max_oi_since_entry:
                return
            self._entries[symbol] = replace(e, max_oi_since_entry=oi)

    def _save_manual_symbols_locked(self) -> None:
        self._manual_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"symbols": sorted(self._manual_symbols)}
        self._manual_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def reason_labels_for(entry: WatchlistEntry) -> list[str]:
    out: list[str] = []
    if WatchlistReason.MANUAL in entry.reasons:
        out.append("手动添加")
    if WatchlistReason.OI_7D_TOP in entry.reasons:
        r = entry.rank_oi7d
        out.append(f"7日OI涨幅榜#{r}" if r is not None else "7日OI涨幅榜")
    if WatchlistReason.OI_1D_UP in entry.reasons:
        out.append("单日OI涨幅超阈值")
    if WatchlistReason.PRICE_1D_UP in entry.reasons:
        out.append("单日价格涨幅超阈值")
    if WatchlistReason.OI_1D_DOWN in entry.reasons:
        out.append("单日OI跌幅超阈值")
    if not out:
        out.append("观察期内保留（当前未命中规则）")
    return out


def _usdt_perpetual_symbols(info: dict) -> list[str]:
    out: list[str] = []
    for s in info.get("symbols", []):
        if s.get("contractType") != "PERPETUAL":
            continue
        if s.get("quoteAsset") != "USDT":
            continue
        if s.get("status") != "TRADING":
            continue
        sym = str(s.get("symbol", "")).upper()
        if sym:
            out.append(sym)
    return out


async def _one_symbol_metrics(client: BinanceFuturesClient, symbol: str) -> dict[str, Any]:
    out: dict[str, Any] = {"symbol": symbol}
    try:
        hist = await client.open_interest_hist(symbol, "1d", 8)
        out["oi_hist"] = hist
        if len(hist) >= 1:
            out["oi_prev_day"] = float(hist[-1]["sumOpenInterest"])
        if len(hist) >= 8:
            out["oi_7d_base"] = float(hist[0]["sumOpenInterest"])
    except Exception as e:
        log.debug("读取 1d OI 历史失败 %s: %s", symbol, e)
    try:
        out["oi_now"] = float((await client.open_interest(symbol))["openInterest"])
    except Exception as e:
        log.debug("读取当前 OI 失败 %s: %s", symbol, e)
    try:
        kl = await client.klines(symbol, "1d", limit=2)
        if len(kl) >= 2:
            out["prev_close"] = float(kl[-2][4])
            out["price_now"] = float(kl[-1][4])
    except Exception as e:
        log.debug("读取 1d K 线失败 %s: %s", symbol, e)
    return out


async def run_watchlist_scan(
    client: BinanceFuturesClient,
    store: WatchlistStore,
    mcap_cache: CoinGeckoMcapCache,
    cfg: dict,
    concurrency: int = 6,
) -> None:
    info = await client.exchange_info()
    symbols = _usdt_perpetual_symbols(info)
    manual_symbols = set(await store.list_manual_symbols())
    wl = cfg.get("watchlist", {})
    top_n = int(wl.get("oi7d", {}).get("topN", 10))
    oi_1d_up = float(wl.get("oi1dUp", {}).get("minPct", 1.0))
    price_1d_up = float(wl.get("price1dUp", {}).get("minPct", 0.30))
    oi_1d_down = float(wl.get("oi1dDown", {}).get("maxPct", -0.50))
    retain_days = int(wl.get("retainDays", 10))
    sem = asyncio.Semaphore(concurrency)

    async def bound(coro: Any) -> Any:
        async with sem:
            return await coro

    log.info("观察列表扫描开始，标的数=%s", len(symbols))
    metrics = await asyncio.gather(*(bound(_one_symbol_metrics(client, s)) for s in symbols))

    oi7d_candidates: list[tuple[str, float]] = []
    auto_rows: dict[str, dict[str, Any]] = {}
    row_by_symbol: dict[str, dict[str, Any]] = {}
    for row in metrics:
        sym = row["symbol"]
        row_by_symbol[sym] = row
        reasons: set[WatchlistReason] = set()
        oi_now = row.get("oi_now")
        oi_prev_day = row.get("oi_prev_day")
        oi_7d_base = row.get("oi_7d_base")
        price_now = row.get("price_now")
        prev_close = row.get("prev_close")

        oi_1d_pct = _metric_pct(oi_now, oi_prev_day)
        if oi_1d_pct is not None and oi_1d_pct >= oi_1d_up:
            reasons.add(WatchlistReason.OI_1D_UP)
        if oi_1d_pct is not None and oi_1d_pct <= oi_1d_down:
            reasons.add(WatchlistReason.OI_1D_DOWN)

        price_1d_pct = _metric_pct(price_now, prev_close)
        if price_1d_pct is not None and price_1d_pct >= price_1d_up:
            reasons.add(WatchlistReason.PRICE_1D_UP)
        oi_7d_pct = _metric_pct(oi_now, oi_7d_base)
        if oi_7d_pct is not None:
            oi7d_candidates.append((sym, oi_7d_pct))

        if reasons:
            auto_rows[sym] = {"reasons": reasons, "entry_price_usdt": price_now, "entry_oi_qty": oi_now}

    oi7d_candidates.sort(key=lambda item: item[1], reverse=True)
    for rank, (sym, _) in enumerate(oi7d_candidates[:top_n], start=1):
        row = auto_rows.setdefault(sym, {"reasons": set()})
        row["reasons"].add(WatchlistReason.OI_7D_TOP)
        row["rank_oi7d"] = rank
        row["entry_price_usdt"] = row_by_symbol.get(sym, {}).get("price_now")
        row["entry_oi_qty"] = row_by_symbol.get(sym, {}).get("oi_now")
    log.info("7日OI涨幅入列 Top%s 完成", top_n)

    for sym in manual_symbols:
        row = auto_rows.setdefault(sym, {"reasons": set()})
        metrics = row_by_symbol.get(sym, {})
        row.setdefault("entry_price_usdt", metrics.get("price_now"))
        row.setdefault("entry_oi_qty", metrics.get("oi_now"))

    await store.reconcile(auto_rows, retain_days=retain_days)
    await mcap_cache.refresh()

    snap = await store.snapshot()
    manual = await store.list_manual_symbols()
    log.info("当前观察列表数量=%s 手动添加=%s", len(snap), len(manual))
    for sym, e in sorted(snap.items()):
        log.info("观察列表 %s 入列时间=%s 原因=%s", sym, e.entry_time.isoformat(), ",".join(reason_labels_for(e)))