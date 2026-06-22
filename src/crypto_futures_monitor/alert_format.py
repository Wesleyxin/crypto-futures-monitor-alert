from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .models import ALERT_TZ, AlertEvent


def to_alert_tz(dt: datetime) -> datetime:
    """统一到告警时区 UTC+8 展示。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ALERT_TZ)


def format_beijing_time(dt: datetime) -> str:
    return to_alert_tz(dt).strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)"


_RULE_TITLE: dict[str, str] = {
    "price_oi_since_watchlist_high": "观察列表 · 持仓量和价格同时突破入列后最高点",
    "price_oi_rolling_7d_high": "观察列表 · 持仓量和价格同时突破7日滚动高点",
    "volume_spike_10m": "观察列表 · 10m成交量涨幅超1000%",
}


def rule_title_cn(rule_type: str) -> str:
    return _RULE_TITLE.get(rule_type, f"监控告警 · {rule_type}")


def _pct(x: Any, digits: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{v * 100:.{digits}f}%"


# 推送里与「规则数值」并列展示的快照字段，避免在「其它」规则里重复打印一大段 JSON
_SNAPSHOT_KEYS = frozenset(
    {
        "open_interest_value_usdt",
        "market_cap_usdt",
        "open_interest_quantity",
        "mark_price_usdt",
        "oi_value_to_mcap_ratio",
        "bar_close_ms",
        "oi_hist_boundary_ms",
    }
)


def _money_usd(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v >= 1e12:
        return f"{v / 1e12:.3f} 万亿"
    if v >= 1e8:
        return f"{v / 1e8:.3f} 亿"
    if v >= 1e6:
        return f"{v / 1e4:.2f} 万"
    return f"{v:,.2f}"


def _num(x: Any, digits: int = 4) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if abs(v) >= 1e8 or (abs(v) < 1e-4 and v != 0):
        return f"{v:.{digits}e}"
    if abs(v - int(v)) < 1e-9:
        return f"{int(v):,}"
    return f"{v:,.{digits}f}".rstrip("0").rstrip(".")


def format_values_cn(rule_type: str, values: dict[str, Any]) -> list[str]:
    """将数值字典格式化为中文多行说明。"""
    lines: list[str] = []
    v = values or {}

    if rule_type == "price_oi_since_watchlist_high":
        lines.append(f"- 当前价格：**{_num(v.get('price'), 4)}**")
        lines.append(f"- 此前入列后价格高点：{_num(v.get('prev_max_price'), 4)}")
        lines.append(f"- 当前持仓量 OI：**{_num(v.get('oi'), 4)}**")
        lines.append(f"- 此前入列后 OI 高点：{_num(v.get('prev_max_oi'), 4)}")
    elif rule_type == "price_oi_rolling_7d_high":
        lines.append(f"- 当前价格：**{_num(v.get('price'), 4)}**")
        lines.append(f"- 此前7日价格高点：{_num(v.get('prev_price_7d_high'), 4)}")
        lines.append(f"- 当前持仓量 OI：**{_num(v.get('oi'), 4)}**")
        lines.append(f"- 此前7日 OI 高点：{_num(v.get('prev_oi_7d_high'), 4)}")
    elif rule_type == "volume_spike_10m":
        lines.append(f"- 当前10m成交量：**{_num(v.get('current_volume_10m'), 6)}**")
        lines.append(f"- 前10m成交量：{_num(v.get('previous_volume_10m'), 6)}")
        lines.append(f"- 10m成交量涨幅：**{_pct(v.get('volume_chg_pct'))}**")
    else:
        rest = {k: val for k, val in v.items() if k not in _SNAPSHOT_KEYS}
        if not rest:
            lines.append("- （无其它扩展字段）")
        else:
            try:
                raw = json.dumps(rest, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                raw = str(rest)
            lines.append("```\n" + raw[:800] + ("\n```" if len(raw) <= 800 else "\n…\n```"))
    return lines


def format_market_snapshot_lines(values: dict[str, Any]) -> list[str]:
    """持仓量、标记价、持仓名义价值、市值、比值（推送/日志用中文多行）。"""
    lines: list[str] = []
    v = values or {}
    qty = v.get("open_interest_quantity")
    if qty is not None:
        lines.append(f"- **持仓量（OI）：** {_num(qty, 6)}")
    else:
        lines.append("- **持仓量（OI）：** 本次未能从交易所拉取")
    mark = v.get("mark_price_usdt")
    if mark is not None:
        lines.append(f"- **标记价格（USDT）：** {_num(mark, 4)}")
    else:
        lines.append("- **标记价格（USDT）：** —")
    oi_val = v.get("open_interest_value_usdt")
    if oi_val is not None:
        lines.append(f"- **持仓名义价值（OI×标记价）：** {_money_usd(oi_val)} USDT")
    else:
        lines.append("- **持仓名义价值：** 本次未能从交易所拉取")
    mcap = v.get("market_cap_usdt")
    if mcap is not None and float(mcap) > 0:
        lines.append(f"- **代币市值（参考 CoinGecko，与入列逻辑同源）：** {_money_usd(mcap)} USD")
    else:
        lines.append("- **代币市值：** 暂无或未命中映射（需开启 CoinGecko 且完成至少一次观察列表扫描以刷新缓存）")
    ratio = v.get("oi_value_to_mcap_ratio")
    if ratio is not None and isinstance(ratio, (int, float)) and mcap is not None and float(mcap) > 0:
        lines.append(f"- **持仓名义价值 / 市值：** {float(ratio):.4f}")
    return lines


def _watchlist_entry_line(event: AlertEvent) -> str:
    if event.watchlist_entry_at is None:
        return "（不适用：大盘动能或非观察列表标的）"
    return format_beijing_time(event.watchlist_entry_at)


def _watchlist_reasons_line(event: AlertEvent) -> str:
    if event.watchlist_reasons:
        return "、".join(event.watchlist_reasons)
    return "（无：本条非基于观察列表条件）"


def _escape_md_line(s: str) -> str:
    """弱化 markdown 特殊字符对排版的影响。"""
    s = s.replace("&", "＆")
    return s


def build_alert_detail_lines(event: AlertEvent) -> list[str]:
    """补充关键异动明细，供企业微信与 Web 面板共用。"""
    v = event.values or {}
    rule_type = event.rule_type
    if rule_type == "price_oi_since_watchlist_high":
        return ["观察列表：持仓量和价格同时突破加入列表以来的最高点"]
    if rule_type == "price_oi_rolling_7d_high":
        return ["观察列表：持仓量和价格同时突破7日滚动高点"]
    if rule_type == "volume_spike_10m":
        return [f"观察列表：10m成交量涨幅{_pct(v.get('volume_chg_pct'))}"]
    return []


def build_alert_lines(event: AlertEvent) -> list[str]:
    """统一告警展示内容，供企业微信与 Web 面板共用。"""
    v = event.values or {}
    price = v.get("mark_price_usdt", v.get("price"))
    oi_value = v.get("open_interest_value_usdt")
    mcap = v.get("market_cap_usdt")
    push_count_today = v.get("push_count_today")
    is_first_push_today = bool(v.get("is_first_push_today"))
    watchlist_entry_at = event.watchlist_entry_at
    lines = [
        "【今日首次】合约监控告警" if is_first_push_today else "合约监控告警",
        f"代币：{event.symbol}",
        f"价格：{_num(price, 4) if price is not None else '—'}",
        f"OI(价值)：{_money_usd(oi_value)} USDT" if oi_value is not None else "OI(价值)：—",
        f"市值：{_money_usd(mcap)} USD" if mcap is not None else "市值：—",
    ]
    if watchlist_entry_at is not None:
        lines.append(f"入列时间：{format_beijing_time(watchlist_entry_at)}")
        lines.append(f"入列原因：{_watchlist_reasons_line(event)}")
    if push_count_today is not None:
        lines.append("次数：今日首次推送" if is_first_push_today else f"次数：今日第{_num(push_count_today, 0)}次推送")
    lines.extend(build_alert_detail_lines(event))
    lines.append(f"告警时间：{format_beijing_time(event.triggered_at)}")
    return lines


def build_wecom_markdown(event: AlertEvent) -> str:
    parts = build_alert_lines(event)
    first_push_today = bool((event.values or {}).get("is_first_push_today"))
    title_line = parts[0]
    if first_push_today:
        title_line = f"<font color=\"info\">**{_escape_md_line(title_line)}**</font>"
    else:
        title_line = _escape_md_line(title_line)
    text = "\n".join(
        [f"## {title_line}"]
        + (["> <font color=\"info\">**今日首次推送**</font>"] if first_push_today else [])
        + [
            _escape_md_line(line.replace(f"代币：{event.symbol}", f"代币：`{event.symbol}`"))
            if line.startswith("代币：")
            else (
                f"<font color=\"info\">**{_escape_md_line(line)}**</font>"
                if first_push_today and line == "次数：今日首次推送"
                else _escape_md_line(line)
            )
            for line in parts[1:]
        ]
    )
    # 企业微信 markdown 单条上限约 4096 字节
    b = text.encode("utf-8")
    if len(b) > 3800:
        text = text.encode("utf-8")[:3700].decode("utf-8", errors="ignore") + "\n\n…（内容过长已截断）"
    return text


def _discord_field(name: str, value: str, inline: bool = False) -> dict[str, Any]:
    v = value.strip() or "—"
    if len(v) > 1024:
        v = v[:1000] + "..."
    return {"name": name[:256], "value": v, "inline": inline}


def build_discord_embed(event: AlertEvent) -> dict[str, Any]:
    v = event.values or {}
    price = v.get("mark_price_usdt", v.get("price"))
    oi_value = v.get("open_interest_value_usdt")
    mcap = v.get("market_cap_usdt")
    is_first_push_today = bool(v.get("is_first_push_today"))
    detail_lines = build_alert_detail_lines(event)
    fields = [
        _discord_field("代币", event.symbol, True),
        _discord_field("规则", rule_title_cn(event.rule_type), False),
        _discord_field("价格", _num(price, 4) if price is not None else "—", True),
        _discord_field("OI(价值)", f"{_money_usd(oi_value)} USDT" if oi_value is not None else "—", True),
        _discord_field("市值", f"{_money_usd(mcap)} USD" if mcap is not None else "—", True),
        _discord_field("次数", "今日首次推送" if is_first_push_today else f"今日第{_num(v.get('push_count_today'), 0)}次推送", True),
    ]
    if event.watchlist_entry_at is not None:
        fields.append(_discord_field("入列时间", format_beijing_time(event.watchlist_entry_at), False))
        fields.append(_discord_field("入列原因", _watchlist_reasons_line(event), False))
    if detail_lines:
        fields.append(_discord_field("明细", "\n".join(detail_lines), False))
    fields.append(_discord_field("告警时间", format_beijing_time(event.triggered_at), False))
    return {
        "title": "【今日首次】合约监控告警" if is_first_push_today else "合约监控告警",
        "color": 3447003 if is_first_push_today else 5793266,
        "fields": fields[:25],
    }


def build_log_line_cn(event: AlertEvent) -> str:
    """供日志一行输出（中文 + 北京时间）。"""
    title = rule_title_cn(event.rule_type)
    t = format_beijing_time(event.triggered_at)
    v = event.values or {}
    price = v.get("mark_price_usdt", v.get("price"))
    oi_v = v.get("open_interest_value_usdt")
    mc = v.get("market_cap_usdt")
    return (
        f"[告警] 代币:{event.symbol} | 价格:{_num(price, 4) if price is not None else '—'} | "
        f"规则:{title} | OI价值:{_money_usd(oi_v)}USDT | 市值:{_money_usd(mc)}USD | 时间:{t}"
    )


def build_generic_webhook_payload(event: AlertEvent) -> dict[str, Any]:
    """通用 Webhook：结构化 JSON，字段中文描述。"""
    v = event.values or {}
    entry_at = event.watchlist_entry_at
    title_cn = rule_title_cn(event.rule_type)
    return {
        "告警类型": title_cn,
        "触发规则": title_cn,
        "规则代码": event.rule_type,
        "交易对": event.symbol,
        "触发时间_北京时间": format_beijing_time(event.triggered_at),
        "加入观察列表时间_北京时间": format_beijing_time(entry_at) if entry_at is not None else None,
        "加入观察列表时间_UTC": entry_at.isoformat() if entry_at is not None else None,
        "加入观察列表原因": event.watchlist_reasons,
        "入列原因": event.watchlist_reasons,
        "说明": event.message,
        "持仓量_OI": v.get("open_interest_quantity"),
        "持仓量": v.get("open_interest_quantity"),
        "标记价_USDT": v.get("mark_price_usdt"),
        "持仓名义价值_USDT": v.get("open_interest_value_usdt"),
        "代币市值_USD": v.get("market_cap_usdt"),
        "持仓名义价值_与_市值_比值": v.get("oi_value_to_mcap_ratio"),
        "今日推送次数": v.get("push_count_today"),
        "是否今日首次推送": v.get("is_first_push_today"),
        "规则数值详情": event.values,
        "关键数值": event.values,
    }
