"""
Alert formatting and delivery.

Three v1 failures are designed out here rather than patched later:

  1. Markdown parse_mode broke on token names containing _ * ` [ — Telegram
     answered 400 and the send failed silently. HTML is used instead, and
     every piece of token-supplied text is escaped.
  2. The CA must stay tappable. <code> renders as copy-on-tap in Telegram.
  3. Sends were nested inside "if not already_tracking", so a token seen once
     never alerted again. Dedupe here is time-based and explicit.
"""

from __future__ import annotations

import html
import time
import logging
from dataclasses import dataclass
from typing import Optional

import requests

import config

log = logging.getLogger("surgeon.alerts")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4096

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})

# ca -> last alert timestamp
_last_alert: dict[str, float] = {}


def esc(v) -> str:
    """Escape anything a token author controls. Names are hostile input."""
    return html.escape(str(v if v is not None else ""), quote=False)


def money(v: float) -> str:
    v = float(v or 0)
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}k"
    return f"${v:,.0f}"


def pct(v: float) -> str:
    v = float(v or 0)
    if abs(v) >= 10_000:
        return f"{v:+,.0f}%"
    return f"{v:+.1f}%"


def price(v: float) -> str:
    v = float(v or 0)
    if v == 0:
        return "$0"
    if v < 0.000001:
        return f"${v:.10f}".rstrip("0")
    if v < 1:
        return f"${v:.8f}".rstrip("0")
    return f"${v:,.4f}".rstrip("0").rstrip(".")


def age(hours: float, known: bool = True) -> str:
    if not known:
        return "age unknown"
    if hours < 1:
        return f"{hours*60:.0f}m"
    if hours < 48:
        return f"{hours:.1f}h"
    return f"{hours/24:.0f}d"


# ── DEDUPE ────────────────────────────────────────────────────────

def should_send(ca: str, cooldown_minutes: Optional[int] = None) -> bool:
    """
    Time-based, not state-based.

    A token already being tracked is not a reason to stay silent — it is
    often a reason to speak, because the setup has strengthened. The only
    thing we suppress is repeating ourselves within the cooldown.
    """
    cd = (cooldown_minutes if cooldown_minutes is not None
          else config.REALERT_COOLDOWN_MINUTES) * 60
    last = _last_alert.get(ca, 0)
    return (time.time() - last) >= cd


def mark_sent(ca: str):
    _last_alert[ca] = time.time()


# ── FORMATTERS ────────────────────────────────────────────────────

TIER_HEADER = {
    "first_moon":  "🌑 FIRST MOON",
    "second_moon": "🌕 SECOND MOON",
    "boosted":     "🚀 BOOSTED",
    "social_call": "📢 CHANNEL CALL",
}

BAND_ICON = {"HIGH": "🔥", "GOOD": "✅", "WATCH": "👀", "SKIP": "💤"}


def format_signal(ev, adapter) -> str:
    """A new signal. ev is a scoring.Evaluation."""
    m, s, c = ev.market, ev.safety, ev.conviction
    head = TIER_HEADER.get(ev.tier.tier, "📡 SIGNAL")
    icon = BAND_ICON.get(c.band, "")

    # Safety standing, stated up front. Every rug that reached King came from
    # the group with nothing flagged — not because it was clean, but because
    # nothing could be checked. That distinction belongs at the top, not
    # buried under the price data.
    unproven = any(l == "unproven" for l, _ in c.components)
    danger = sum(1 for f in c.risk_flags if f.severity == "danger")

    if not s.verified:
        standing = "🔴 UNVERIFIED — no safety source answered"
    elif unproven:
        # Stated even when flags exist, because this is the state that
        # produced every rug that got through: nothing detected, because
        # there was nothing yet to detect.
        extra = f" · 🚩 {len(c.risk_flags)}" if c.risk_flags else ""
        standing = f"🟠 UNPROVEN — too new to verify{extra}"
    elif c.risk_flags:
        word = "flag" if len(c.risk_flags) == 1 else "flags"
        standing = (f"🚩 {len(c.risk_flags)} {word}"
                    + (f", {danger} severe" if danger else "")
                    + f" — {esc(c.risk_flags[0].code)}")
    else:
        standing = "🟢 CLEAN — checked, nothing flagged"

    lines = [
        f"{head} · {esc(adapter.display)} {icon}",
        "",
        f"<b>{esc(m.name)}</b> ({esc(m.symbol)})",
        f"{standing}",
        f"⚡ Conviction <b>{c.score}/100</b> · {c.band} · {c.momentum}",
        "",
        f"💧 Liq {money(m.liquidity_usd)}   📊 FDV {money(m.fdv)}",
        f"📈 5m {pct(m.change_5m)}   1h {pct(m.change_1h)}   24h {pct(m.change_24h)}",
        f"🔁 {m.buys_5m}b / {m.sells_5m}s (5m)   💵 vol24h {money(m.volume_24h)}",
        f"🕐 {age(m.age_hours, m.age_known)}   ·   {esc(m.dex or 'unknown dex')}"
        + (f"   ·   {esc(m.launchpad)}" if m.launchpad else ""),
    ]

    called = getattr(ev, "called_by", None)
    if called:
        word = "channel" if len(called) == 1 else "channels"
        lines.append(f"📢 Called by {len(called)} {word}: "
                     f"<b>{esc(', '.join(called[:4]))}</b>"
                     + (f" +{len(called) - 4} more" if len(called) > 4 else ""))

    if c.meta_term:
        lines.append(f"🔥 Riding the <b>{esc(c.meta_term)}</b> meta")

    if c.social_channels or c.smart_wallets:
        extra = []
        if c.social_channels:
            extra.append(f"📡 {c.social_channels} channels")
        if c.smart_wallets:
            extra.append(f"💎 {c.smart_wallets} smart wallets")
        lines.append("   ·   ".join(extra))

    lines += ["", f"🔐 {esc(s.display())}"]

    if not s.verified:
        lines.append("⚠️ <b>No safety source responded — treat as unverified</b>")
    elif s.partial:
        missing = ", ".join(s.unavailable[:3])
        lines.append(f"⚠️ Unchecked: {esc(missing)}")

    issues = m.sanity_issues
    if issues:
        lines.append(f"⚠️ Suspect data: {esc(', '.join(issues[:3]))}")

    if c.risk_flags:
        lines.append("")
        lines.append("🚩 <b>Scam checks</b>")
        for f in c.risk_flags[:5]:
            mark = "🔴" if f.severity == "danger" else "🟡"
            lines.append(f"{mark} {esc(f.code)} — {esc(f.detail)} ({f.penalty})")

    lines += [
        "",
        f"<code>{esc(m.ca)}</code>",
        "",
        f'<a href="{adapter.chart_url(m.ca)}">chart</a> · '
        f'<a href="{adapter.explorer_url(m.ca)}">explorer</a>',
        "",
        f"<i>{esc(c.explain())}</i>",
        "",
        "📋 SIGNAL ONLY — you place the trade",
    ]
    return "\n".join(lines)


def format_velocity(ca: str, name: str, channels: list[str],
                    adapter, market=None) -> str:
    lines = [
        f"📡 <b>VELOCITY</b> · {len(channels)} channels · {esc(adapter.display)}",
        "",
        f"<b>{esc(name)}</b>",
        f"Called by: {esc(', '.join(channels[:6]))}",
    ]
    if market and market.ok:
        lines += [
            "",
            f"💧 Liq {money(market.liquidity_usd)}   📊 FDV {money(market.fdv)}",
            f"📈 1h {pct(market.change_1h)}   🕐 {age(market.age_hours, market.age_known)}",
        ]
    lines += ["", f"<code>{esc(ca)}</code>", "",
              f'<a href="{adapter.chart_url(ca)}">chart</a>']
    return "\n".join(lines)


WATCH_HEADERS = {
    "TP1":          ("🎯", "TP1 HIT"),
    "TP2":          ("🎯", "TP2 HIT"),
    "TP3":          ("🚀", "TP3 HIT"),
    "STOP_WARN":    ("⚠️", "GOING AGAINST YOU"),
    "STOP_LOSS":    ("🛑", "STOP LOSS"),
    "TRAIL_STOP":   ("🛑", "TRAILING STOP"),
    "VOLUME_FADE":  ("📉", "VOLUME FADING"),
    "DEV_SOLD":     ("🚨", "DEV WALLET SOLD"),
    "WHALE_STOP":   ("🐋", "WHALE APPEARED"),
    "TIME_STOP":    ("⏰", "TIME STOP"),
    "GRADUATION":   ("🎓", "GRADUATING"),
}


def format_watch(event: str, name: str, ca: str, pnl: float,
                 adapter, detail: str = "") -> str:
    icon, label = WATCH_HEADERS.get(event, ("📊", event))
    lines = [
        f"{icon} <b>{label}</b> · {esc(adapter.display)}",
        "",
        f"<b>{esc(name)}</b>",
        f"PnL since signal: <b>{pct(pnl)}</b>",
    ]
    if detail:
        lines.append(esc(detail))
    lines += ["", f"<code>{esc(ca)}</code>", "",
              f'<a href="{adapter.chart_url(ca)}">chart</a>']
    return "\n".join(lines)


# ── DELIVERY ──────────────────────────────────────────────────────

@dataclass
class SendResult:
    ok: bool
    error: Optional[str] = None
    message_id: Optional[int] = None


def send(text: str, chat_id: Optional[str] = None,
         disable_preview: bool = True, retries: int = 2) -> SendResult:
    """
    Deliver one message. Returns a result rather than raising — a failed
    alert must never take the scanner down with it.
    """
    token = config.TELEGRAM_BOT_TOKEN
    chat = chat_id or config.TELEGRAM_CHAT_ID
    if not token or not chat:
        return SendResult(False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")

    if len(text) > MAX_LEN:
        text = text[:MAX_LEN - 20].rsplit("\n", 1)[0] + "\n…"

    payload = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }

    delay = 1.0
    for attempt in range(retries + 1):
        try:
            r = _session.post(TELEGRAM_API.format(token=token),
                              json=payload, timeout=15)
            data = r.json()
            if data.get("ok"):
                return SendResult(True, message_id=(data.get("result") or {}).get("message_id"))

            desc = data.get("description", "unknown error")
            # 429 carries retry_after; anything 4xx other than that is our bug
            if r.status_code == 429:
                wait = (data.get("parameters") or {}).get("retry_after", 5)
                time.sleep(wait)
                continue
            if 400 <= r.status_code < 500:
                log.error("telegram rejected message: %s", desc)
                return SendResult(False, desc)
            time.sleep(delay); delay *= 2
        except Exception as e:
            if attempt < retries:
                time.sleep(delay); delay *= 2
                continue
            return SendResult(False, str(e))
    return SendResult(False, "retries exhausted")


def send_signal(ev, adapter, force: bool = False) -> SendResult:
    """Format, dedupe and deliver a signal."""
    if not force and not should_send(ev.market.ca):
        return SendResult(False, "cooldown")
    res = send(format_signal(ev, adapter))
    if res.ok:
        mark_sent(ev.market.ca)
    return res
