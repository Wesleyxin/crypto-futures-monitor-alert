from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

from .binance import BinanceFuturesClient
from .coingecko import CoinGeckoMcapCache
from .alert_format import format_beijing_time
from .models import WatchlistEntry
from .recent_buffer import RecentAlertsBuffer
from .rule_toggles import RuleToggleStore
from .watchlist import WatchlistStore, reason_labels_for

log = logging.getLogger(__name__)

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def _no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


def _fmt_num(v: Any, digits: int = 4) -> Optional[str]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if abs(n - int(n)) < 1e-9:
        return f"{int(n):,}"
    return f"{n:,.{digits}f}".rstrip("0").rstrip(".")


def _fmt_money(v: Any) -> Optional[str]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n >= 1e12:
        return f"{n / 1e12:.3f} 万亿"
    if n >= 1e8:
        return f"{n / 1e8:.3f} 亿"
    if n >= 1e6:
        return f"{n / 1e4:.2f} 万"
    return f"{n:,.2f}"


async def _entry_to_dict(
    e: WatchlistEntry, client: Optional[BinanceFuturesClient], mcap: Optional[CoinGeckoMcapCache]
) -> dict[str, Any]:
    price_now: Optional[float] = None
    oi_qty: Optional[float] = None
    oi_value: Optional[float] = None
    market_cap: Optional[float] = None
    if client is not None:
        try:
            oi_r, mp_r = await asyncio.gather(client.open_interest(e.symbol), client.mark_price(e.symbol))
            oi_qty = float(oi_r["openInterest"])
            price_now = float(mp_r["markPrice"])
            oi_value = oi_qty * price_now
        except Exception:
            pass
    if mcap is not None and mcap.enabled:
        try:
            market_cap = await mcap.market_cap_usd(e.symbol)
        except Exception:
            market_cap = None
    gain_pct = None
    if e.entry_price_usdt is not None and price_now is not None and abs(e.entry_price_usdt) > 1e-12:
        gain_pct = (price_now - e.entry_price_usdt) / abs(e.entry_price_usdt)
    return {
        "symbol": e.symbol,
        "entry_time": e.entry_time.isoformat(),
        "entry_time_beijing": format_beijing_time(e.entry_time),
        "reasons": [r.value for r in sorted(e.reasons, key=lambda x: x.value)],
        "reason_labels": reason_labels_for(e),
        "rank_oi7d": e.rank_oi7d,
        "entry_price_usdt": e.entry_price_usdt,
        "entry_price_display": _fmt_num(e.entry_price_usdt),
        "price_now_usdt": price_now,
        "price_now_display": _fmt_num(price_now),
        "open_interest_value_usdt": oi_value,
        "open_interest_value_display": _fmt_money(oi_value),
        "market_cap_usdt": market_cap,
        "market_cap_display": _fmt_money(market_cap),
        "gain_since_entry_pct": gain_pct,
        "max_oi_since_entry": e.max_oi_since_entry,
        "max_price_since_entry": e.max_price_since_entry,
    }


def _auth_ok(request: web.Request, token: str) -> bool:
    if not token:
        return True
    if request.query.get("token", "") == token:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() == token
    return False


def _auth_middleware_factory(token: str):
    @web.middleware
    async def middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
        path = request.path
        if path == "/api/health":
            return await handler(request)
        if token and not _auth_ok(request, token):
            if path == "/":
                return web.Response(
                    status=401,
                    text="访问被拒绝：请在 URL 添加 ?token=（与配置 ui.authToken 相同）",
                    content_type="text/plain",
                    charset="utf-8",
                )
            if path.startswith("/api/"):
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    return middleware


_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>合约监控看板</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --border: #2d3a4d;
      --text: #e7ecf3;
      --muted: #8b9bb4;
      --accent: #3d8bfd;
      --ok: #3ecf8e;
      --warn: #f5a524;
      --danger: #ff6b6b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg); color: var(--text); min-height: 100vh;
    }
    header {
      padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; justify-content: space-between;
      background: linear-gradient(180deg, #15202b 0%, var(--bg) 100%);
    }
    h1 { margin: 0; font-size: 1.15rem; font-weight: 600; letter-spacing: 0.02em; }
    .meta { color: var(--muted); font-size: 0.85rem; }
    main { padding: 1rem 1.25rem 2rem; max-width: 1200px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem; }
    .card {
      background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
      padding: 0.9rem 1rem;
    }
    .card h2 { margin: 0 0 0.35rem; font-size: 0.78rem; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
    .card .num { font-size: 1.65rem; font-weight: 700; font-variant-numeric: tabular-nums; }
    .section-title { font-size: 0.95rem; margin: 1.25rem 0 0.5rem; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
    th, td { padding: 0.55rem 0.65rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-weight: 500; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; background: #131c28; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(61, 139, 253, 0.06); }
    .pill { display: inline-block; padding: 0.12rem 0.45rem; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }
    .pill-default { background: rgba(61, 139, 253, 0.12); color: var(--accent); }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.78rem; word-break: break-all; }
    .err { color: var(--danger); font-size: 0.85rem; margin-top: 0.5rem; }
    .split { display:grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 1rem; align-items:start; }
    .left-stack { display:flex; flex-direction:column; gap:1rem; min-width:0; }
    .sticky { position: sticky; top: 1rem; }
    .stack { display:flex; flex-direction:column; gap:0.75rem; }
    .alert-toolbar { display:flex; align-items:center; justify-content:space-between; gap:0.5rem; margin-bottom:0.5rem; }
    .alert-scroll { max-height: 82vh; overflow-y: auto; padding-right: 0.2rem; scrollbar-width: thin; }
    .alert-scroll::-webkit-scrollbar { width: 6px; }
    .alert-scroll::-webkit-scrollbar-thumb { background: rgba(139, 155, 180, 0.35); border-radius: 999px; }
    .alert-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 0.8rem 0.85rem; }
    .alert-card.first-push {
      border-color: rgba(61, 139, 253, 0.7);
      background: linear-gradient(180deg, rgba(61, 139, 253, 0.18) 0%, rgba(14, 24, 40, 0.98) 100%);
      box-shadow: 0 0 0 1px rgba(61, 139, 253, 0.18), 0 10px 24px rgba(61, 139, 253, 0.16);
    }
    .alert-card.first-push .alert-title,
    .alert-card.first-push .alert-lines .line.title {
      color: #7fb0ff;
      font-weight: 800;
    }
    .alert-head { display:flex; align-items:flex-start; justify-content:space-between; gap:0.5rem; margin-bottom:0.4rem; }
    .alert-title { font-size:0.92rem; font-weight:600; line-height:1.25; }
    .first-push-badge {
      display:inline-flex; align-items:center; gap:0.25rem; margin-top:0.28rem;
      padding:0.14rem 0.5rem; border-radius:999px; font-size:0.72rem; font-weight:700;
      color:#eef5ff; background:rgba(61, 139, 253, 0.92);
    }
    .alert-time { color: var(--muted); font-size:0.74rem; line-height:1.35; margin-bottom:0.35rem; }
    .alert-line { font-size:0.8rem; line-height:1.45; color: var(--text); }
    .alert-sub { color: var(--muted); font-size:0.76rem; line-height:1.4; margin-top:0.35rem; }
    .alert-lines { display:flex; flex-direction:column; gap:0.22rem; }
    .alert-lines .line { font-size:0.8rem; line-height:1.45; color: var(--text); word-break: break-word; }
    .alert-lines .line.title { font-weight:600; color: var(--text); margin-bottom:0.2rem; }
    .sound-btn {
      background: transparent; color: var(--muted); border: 1px solid var(--border); border-radius: 999px;
      padding: 0.25rem 0.65rem; font-size: 0.74rem; cursor: pointer;
    }
    .sound-btn.active { color: var(--ok); border-color: rgba(62, 207, 142, 0.45); background: rgba(62, 207, 142, 0.08); }
    .toggle-group { color: var(--muted); font-size:0.72rem; margin-bottom:0.18rem; }
    .toggle-btn {
      border:none; border-radius:999px; padding:0.35rem 0.75rem; cursor:pointer; font-size:0.74rem; min-width:62px;
      color:#fff; background:var(--danger);
    }
    .toggle-btn.on { background:var(--ok); color:#0a1510; }
    .rule-control-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:0.75rem; margin-top:0.75rem; }
    .rule-control-card {
      display:flex; flex-direction:column; gap:0.75rem; padding:0.8rem 0.85rem;
      border:1px solid var(--border); border-radius:10px; background:#101826;
    }
    .control-head { display:flex; align-items:flex-start; justify-content:space-between; gap:0.75rem; }
    .control-copy { min-width:0; }
    .control-title { font-size:0.84rem; line-height:1.35; word-break:break-word; }
    .control-sub { color:var(--muted); font-size:0.75rem; }
    .threshold-list { display:flex; flex-direction:column; gap:0.5rem; }
    .threshold-item { display:flex; flex-direction:column; gap:0.3rem; }
    .threshold-title { font-size:0.78rem; line-height:1.35; }
    .threshold-row { display:flex; align-items:center; gap:0.45rem; }
    .threshold-input {
      flex:1; min-width:0; background:#0d1522; color:var(--text); border:1px solid var(--border); border-radius:8px;
      padding:0.5rem 0.65rem; font-size:0.8rem;
    }
    .threshold-unit { color:var(--muted); font-size:0.76rem; white-space:nowrap; }
    .threshold-save {
      background:var(--accent); color:#fff; border:none; border-radius:8px; padding:0.48rem 0.75rem; cursor:pointer; font-size:0.76rem;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>加密货币合约监控</h1>
      <div class="meta" id="clock">加载中…</div>
    </div>
    <div class="meta" id="status"></div>
  </header>
  <main>
    <div class="split">
      <section class="left-stack">
        <div class="grid">
          <div class="card"><h2>观察列表</h2><div class="num" id="cWatch">0</div></div>
          <div class="card"><h2>缓冲区告警条数</h2><div class="num" id="cAlert">0</div></div>
          <div class="card"><h2>刷新间隔</h2><div class="num">10s</div></div>
        </div>
        <div class="card">
          <h2>手动添加观察币</h2>
          <div style="display:flex; gap:0.5rem; flex-wrap:wrap">
            <input id="manualSymbol" placeholder="例如 DOGEUSDT" style="flex:1; min-width:220px; background:#101826; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:0.65rem 0.8rem" />
            <button id="manualAddBtn" style="background:var(--accent); color:#fff; border:none; border-radius:8px; padding:0.65rem 1rem; cursor:pointer">添加</button>
          </div>
          <div class="meta" style="margin-top:0.5rem">手动添加会持久化保存，重启后仍保留。</div>
          <div id="manualMsg" class="err" style="display:none"></div>
        </div>
        <div>
          <div class="section-title">观察列表（全部代币详情）</div>
          <div id="eWatch" class="err" style="display:none"></div>
          <table>
            <thead><tr><th>标的</th><th>加入时间 (UTC+8)</th><th>加入原因</th><th>当前价格</th><th>持仓价值</th><th>市值</th><th>加入后涨幅</th><th>OI榜</th><th>操作</th></tr></thead>
            <tbody id="tWatch"><tr><td colspan="9" class="mono" style="color:var(--muted)">暂无数据</td></tr></tbody>
          </table>
        </div>
        <div class="card">
          <h2>规则开关</h2>
          <div class="meta">当前仅保留两条“同时新高”推送规则；修改后立即生效并持久化保存。</div>
          <div id="controlMsg" class="err" style="display:none"></div>
          <div id="ruleControls" class="rule-control-grid">
            <div class="mono" style="color:var(--muted)">加载中…</div>
          </div>
        </div>
      </section>
      <aside class="sticky">
        <div class="alert-toolbar">
          <div class="section-title" style="margin:0">告警信息</div>
          <button id="soundToggleBtn" class="sound-btn">声音：关</button>
        </div>
        <div id="eAlerts" class="err" style="display:none"></div>
        <div id="alertScroll" class="alert-scroll">
          <div id="alertCards" class="stack">
            <div class="alert-card"><div class="mono" style="color:var(--muted)">暂无告警</div></div>
          </div>
        </div>
      </aside>
    </div>
  </main>
  <script>
    const TOKEN = new URLSearchParams(location.search).get("token") || "";
    let audioCtx = null;
    let lastAlertKeys = [];
    let soundEnabled = localStorage.getItem("monitorSoundEnabled") === "1";
    function q(url) {
      if (!TOKEN) return url;
      const sep = url.includes("?") ? "&" : "?";
      return url + sep + "token=" + encodeURIComponent(TOKEN);
    }
    async function api(url, options) {
      const resp = await fetch(q(url), options);
      const text = await resp.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_) {}
      if (!resp.ok) throw new Error((data && data.error) || ("HTTP " + resp.status));
      return data;
    }
    function pill(rule) {
      if (!rule) return "pill pill-default";
      return "pill pill-default";
    }
    function alertKey(row) {
      return [row.symbol || "", row.rule_type || "", row.triggered_at_utc || row.triggered_at_beijing || "", row.message || ""].join("|");
    }
    function refreshSoundButton() {
      const btn = document.getElementById("soundToggleBtn");
      btn.textContent = soundEnabled ? "声音：开" : "声音：关";
      btn.classList.toggle("active", soundEnabled);
    }
    async function ensureAudioContext() {
      if (!audioCtx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        audioCtx = new Ctx();
      }
      if (audioCtx.state === "suspended") {
        try { await audioCtx.resume(); } catch (_) {}
      }
      return audioCtx;
    }
    async function playAlertSound(newCount) {
      if (!soundEnabled) return;
      const ctx = await ensureAudioContext();
      if (!ctx) return;
      const beeps = Math.max(1, Math.min(Number(newCount) || 1, 3));
      for (let i = 0; i < beeps; i++) {
        const when = ctx.currentTime + i * 0.26;
        const master = ctx.createGain();
        master.gain.setValueAtTime(0.0001, when);
        master.gain.exponentialRampToValueAtTime(0.18, when + 0.02);
        master.gain.exponentialRampToValueAtTime(0.0001, when + 0.24);
        master.connect(ctx.destination);

        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        osc1.type = "triangle";
        osc2.type = "sine";
        osc1.frequency.setValueAtTime(1046.5, when);
        osc2.frequency.setValueAtTime(1318.5, when);

        const gain1 = ctx.createGain();
        const gain2 = ctx.createGain();
        gain1.gain.setValueAtTime(0.9, when);
        gain2.gain.setValueAtTime(0.55, when);

        osc1.connect(gain1);
        osc2.connect(gain2);
        gain1.connect(master);
        gain2.connect(master);

        osc1.start(when);
        osc2.start(when);
        osc1.stop(when + 0.26);
        osc2.stop(when + 0.26);
      }
    }
    function syncNewAlertFeedback(items) {
      const keys = (items || []).map(alertKey);
      if (lastAlertKeys.length) {
        const prev = new Set(lastAlertKeys);
        const newCount = keys.filter(k => !prev.has(k)).length;
        if (newCount > 0) playAlertSound(newCount);
      }
      lastAlertKeys = keys.slice(0, 200);
    }
    function renderRuleControls(ruleItems) {
      const box = document.getElementById("ruleControls");
      const items = Array.isArray(ruleItems) ? ruleItems : [];
      box.innerHTML = "";
      if (!items.length) {
        box.innerHTML = '<div class="mono" style="color:var(--muted)">暂无可配置规则</div>';
        return;
      }
      for (const row of items) {
        const card = document.createElement("div");
        const enabled = !!row.enabled;
        card.className = "rule-control-card";
        card.innerHTML = `<div class="control-head">
            <div class="control-copy">
              <div class="toggle-group">${String(row.group || "").replace(/</g,"&lt;")}</div>
              <div class="control-title">${String(row.title || "").replace(/</g,"&lt;")}</div>
            </div>
            <button class="toggle-btn ${enabled ? "on" : ""}" data-rule="${String(row.rule_type || "").replace(/"/g,"&quot;")}" data-enabled="${enabled ? "1" : "0"}">${enabled ? "已开启" : "已关闭"}</button>
          </div>
          <div class="control-sub">仅保留观察列表中的“同时新高”推送规则。</div>`;
        box.appendChild(card);
      }
      box.querySelectorAll("button[data-rule]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const rule = btn.dataset.rule || "";
          const enabled = btn.dataset.enabled === "1";
          const msg = document.getElementById("controlMsg");
          try {
            await api("/api/rule-toggles/" + encodeURIComponent(rule), {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ enabled: !enabled }),
            });
            msg.style.display = "none";
            await tick();
          } catch (e) {
            msg.style.display = "block";
            msg.textContent = String(e);
          }
        });
      });
    }
    async function tick() {
      document.getElementById("clock").textContent = new Date().toISOString().replace("T"," ").slice(0,19) + "Z";
      document.getElementById("status").textContent = "拉取数据中…";
      try {
        const [a, w, rt] = await Promise.all([
          fetch(q("/api/alerts")).then(r => { if (!r.ok) throw new Error("alerts " + r.status); return r.json(); }),
          fetch(q("/api/watchlist")).then(r => { if (!r.ok) throw new Error("watchlist " + r.status); return r.json(); }),
          fetch(q("/api/rule-toggles")).then(r => { if (!r.ok) throw new Error("rule-toggles " + r.status); return r.json(); }),
        ]);
        document.getElementById("eAlerts").style.display = "none";
        document.getElementById("eWatch").style.display = "none";
        document.getElementById("controlMsg").style.display = "none";
        document.getElementById("cWatch").textContent = w.count ?? 0;
        document.getElementById("cAlert").textContent = (a.items || []).length;
        syncNewAlertFeedback(a.items || []);
        renderRuleControls(rt.items || []);
        const alertCards = document.getElementById("alertCards");
        alertCards.innerHTML = "";
        if (!a.items || !a.items.length) {
          alertCards.innerHTML = '<div class="alert-card"><div class="mono" style="color:var(--muted)">暂无告警</div></div>';
        } else {
          for (const row of a.items) {
            const card = document.createElement("div");
            const ruleLabel = row.rule_title || row.rule_type || "";
            const firstPushToday = !!(row.values && row.values.is_first_push_today);
            const lines = Array.isArray(row.display_lines) && row.display_lines.length ? row.display_lines : [
              "合约监控告警",
              `代币：${row.symbol || ""}`,
              `规则：${ruleLabel}`,
              `时间：${(row.triggered_at_beijing || row.triggered_at_utc || "").replace("（北京时间）","").trim()}`,
            ];
            card.className = firstPushToday ? "alert-card first-push" : "alert-card";
            card.innerHTML = `<div class="alert-head">
                <div>
                  <div class="alert-title">${(row.symbol || "").replace(/</g,"&lt;")}</div>
                  ${firstPushToday ? '<div class="first-push-badge">今日首次</div>' : ""}
                </div>
                <span class="${pill(row.rule_type)}">${ruleLabel.replace(/</g,"&lt;")}</span>
              </div>
              <div class="alert-lines">
                ${lines.map((line, idx) => `<div class="line${idx === 0 ? " title" : ""}">${String(line || "").replace(/</g,"&lt;")}</div>`).join("")}
              </div>`;
            alertCards.appendChild(card);
          }
        }
        const tw = document.getElementById("tWatch");
        tw.innerHTML = "";
        if (!w.items || !w.items.length) {
          tw.innerHTML = '<tr><td colspan="9" class="mono" style="color:var(--muted)">观察列表为空（等待首次扫描）</td></tr>';
        } else {
          for (const row of w.items) {
            const tr = document.createElement("tr");
            const labels = (row.reason_labels || []).join("；");
            const isManual = (row.reasons || []).includes("manual");
            const gain = row.gain_since_entry_pct != null ? (row.gain_since_entry_pct * 100).toFixed(2) + "%" : "-";
            tr.innerHTML = `<td><strong>${row.symbol || ""}</strong></td>
              <td class="mono">${(row.entry_time_beijing || row.entry_time || "").replace("（北京时间）","").trim()}</td>
              <td>${labels.replace(/</g,"&lt;")}</td>
              <td class="mono">${row.price_now_display || "-"}</td>
              <td class="mono">${row.open_interest_value_display ? row.open_interest_value_display + " USDT" : "-"}</td>
              <td class="mono">${row.market_cap_display ? row.market_cap_display + " USD" : "-"}</td>
              <td class="mono">${gain}</td>
              <td class="mono">${row.rank_oi7d != null ? "#" + row.rank_oi7d : "-"}</td>
              <td>${isManual ? `<button data-remove="${row.symbol}" style="background:transparent;color:var(--danger);border:1px solid var(--danger);border-radius:6px;padding:0.25rem 0.5rem;cursor:pointer">移除手动</button>` : '<span class="meta">自动</span>'}</td>`;
            tw.appendChild(tr);
          }
          tw.querySelectorAll("button[data-remove]").forEach((btn) => {
            btn.addEventListener("click", async () => {
              try {
                await api("/api/watchlist/manual/" + encodeURIComponent(btn.dataset.remove), { method: "DELETE" });
                document.getElementById("manualMsg").style.display = "none";
                await tick();
              } catch (e) {
                const el = document.getElementById("manualMsg");
                el.style.display = "block";
                el.textContent = String(e);
              }
            });
          });
        }
        document.getElementById("status").textContent = "已更新";
      } catch (e) {
        document.getElementById("status").textContent = "请求失败";
        const el = document.getElementById("eAlerts");
        el.style.display = "block";
        el.textContent = String(e);
      }
    }
    document.getElementById("soundToggleBtn").addEventListener("click", async () => {
      soundEnabled = !soundEnabled;
      localStorage.setItem("monitorSoundEnabled", soundEnabled ? "1" : "0");
      refreshSoundButton();
      if (soundEnabled) {
        await ensureAudioContext();
        playAlertSound(1);
      }
    });
    document.addEventListener("click", () => { if (soundEnabled) ensureAudioContext(); }, { passive: true });
    refreshSoundButton();
    document.getElementById("manualAddBtn").addEventListener("click", async () => {
      const el = document.getElementById("manualMsg");
      const sym = (document.getElementById("manualSymbol").value || "").trim().toUpperCase();
      if (!sym) {
        el.style.display = "block";
        el.textContent = "请输入交易对，例如 DOGEUSDT";
        return;
      }
      try {
        await api("/api/watchlist/manual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: sym }),
        });
        document.getElementById("manualSymbol").value = "";
        el.style.display = "none";
        await tick();
      } catch (e) {
        el.style.display = "block";
        el.textContent = String(e);
      }
    });
    tick();
    setInterval(tick, 10000);
  </script>
</body>
</html>"""


def create_dashboard_app(
    store: WatchlistStore,
    recent: RecentAlertsBuffer,
    cfg: dict[str, Any],
    client: Optional[BinanceFuturesClient] = None,
    mcap: Optional[CoinGeckoMcapCache] = None,
    rule_toggles: Optional[RuleToggleStore] = None,
) -> web.Application:
    ui = cfg.get("ui", {})
    token = str(ui.get("authToken", "") or "").strip()

    async def index(_: web.Request) -> web.StreamResponse:
        return web.Response(
            text=_INDEX_HTML,
            content_type="text/html",
            charset="utf-8",
            headers=_no_cache_headers(),
        )

    async def api_alerts(_: web.Request) -> web.StreamResponse:
        items = await recent.list_recent()
        return web.json_response({"items": items}, headers=_no_cache_headers())

    async def api_watchlist(_: web.Request) -> web.StreamResponse:
        snap = await store.snapshot()
        rows = await asyncio.gather(*[_entry_to_dict(e, client, mcap) for _, e in sorted(snap.items(), key=lambda kv: kv[0])])
        return web.json_response({"count": len(rows), "items": rows}, headers=_no_cache_headers())

    async def api_rule_toggles(_: web.Request) -> web.StreamResponse:
        items = await rule_toggles.list_items() if rule_toggles is not None else []
        return web.json_response({"items": items}, headers=_no_cache_headers())

    async def api_rule_toggle_update(request: web.Request) -> web.StreamResponse:
        if rule_toggles is None:
            return web.json_response({"error": "规则开关未启用"}, status=400)
        rule_type = str(request.match_info.get("rule_type", "")).strip()
        if not rule_type:
            return web.json_response({"error": "缺少 rule_type"}, status=400)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        if "enabled" not in (data or {}):
            return web.json_response({"error": "缺少 enabled"}, status=400)
        try:
            enabled = await rule_toggles.set_enabled(rule_type, bool(data.get("enabled")))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "rule_type": rule_type, "enabled": enabled}, headers=_no_cache_headers())

    async def api_watchlist_manual_add(request: web.Request) -> web.StreamResponse:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "请求体必须是 JSON"}, status=400)
        symbol = str((data or {}).get("symbol", "")).strip()
        if not symbol:
            return web.json_response({"error": "缺少 symbol"}, status=400)
        try:
            sym = await store.add_manual_symbol(symbol)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        if client is not None:
            try:
                price = float((await client.mark_price(sym))["markPrice"])
                await store.set_entry_price_if_missing(sym, price)
            except Exception:
                pass
            try:
                oi = float((await client.open_interest(sym))["openInterest"])
                await store.set_entry_oi_if_missing(sym, oi)
            except Exception:
                pass
        return web.json_response({"ok": True, "symbol": sym}, headers=_no_cache_headers())

    async def api_watchlist_manual_remove(request: web.Request) -> web.StreamResponse:
        sym = str(request.match_info.get("symbol", "")).strip()
        if not sym:
            return web.json_response({"error": "缺少 symbol"}, status=400)
        removed = await store.remove_manual_symbol(sym)
        return web.json_response({"ok": True, "removed": removed, "symbol": sym.upper()}, headers=_no_cache_headers())

    async def health(_: web.Request) -> web.StreamResponse:
        return web.json_response({"status": "ok"}, headers=_no_cache_headers())

    app = web.Application(middlewares=[_auth_middleware_factory(token)])
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/alerts", api_alerts)
    app.router.add_get("/api/watchlist", api_watchlist)
    app.router.add_get("/api/rule-toggles", api_rule_toggles)
    app.router.add_post("/api/rule-toggles/{rule_type}", api_rule_toggle_update)
    app.router.add_post("/api/watchlist/manual", api_watchlist_manual_add)
    app.router.add_delete("/api/watchlist/manual/{symbol}", api_watchlist_manual_remove)
    return app


async def run_dashboard_server(
    stop: asyncio.Event,
    store: WatchlistStore,
    recent: RecentAlertsBuffer,
    cfg: dict[str, Any],
    client: Optional[BinanceFuturesClient] = None,
    mcap: Optional[CoinGeckoMcapCache] = None,
    rule_toggles: Optional[RuleToggleStore] = None,
) -> None:
    ui = cfg.get("ui", {})
    if not bool(ui.get("enabled", True)):
        return

    host = str(ui.get("host", "0.0.0.0"))
    port = int(os.environ.get("MONITOR_UI_PORT") or ui.get("port", 8765))
    app = create_dashboard_app(
        store,
        recent,
        cfg,
        client=client,
        mcap=mcap,
        rule_toggles=rule_toggles,
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    try:
        await site.start()
    except OSError as e:
        log.error(
            "可视化看板未能绑定 %s:%s（端口占用或无权绑定）。可修改 config 中 ui.port 或设置环境变量 MONITOR_UI_PORT。"
            " 监控其余功能仍继续运行。详情: %s",
            host,
            port,
            e,
        )
        await runner.cleanup()
        await stop.wait()
        return
    log.info("可视化看板: http://%s:%s/ （若配置了 ui.authToken，请使用 ?token= 访问接口与页面）", host, port)
    try:
        await stop.wait()
    finally:
        await runner.cleanup()
