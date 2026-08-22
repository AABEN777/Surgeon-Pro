#!/usr/bin/env python3
"""
Contract analyzer.

Paste an address and get back exactly what Surgeon computes for it and which
gate decides its fate. Built because "would Surgeon have caught this?" kept
being answered by reasoning about thresholds instead of running them.

    python3 analyze.py <address>            print the readout
    python3 analyze.py <address> --send     also push it to Telegram
    python3 analyze.py --poll               answer addresses sent to the bot

Chain is detected from the address format, then resolved by asking which
chain actually has liquidity for it.
"""

from __future__ import annotations

import sys
import time
import logging
import argparse

import config
import chains
import scoring
import risk
import alerts
import meta as meta_mod
import smartmoney
from store import store

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("surgeon.analyze")


# ── ANALYSIS ──────────────────────────────────────────────────────

def analyze(address: str) -> dict:
    """Everything Surgeon knows about one contract."""
    address = (address or "").strip()
    out = {"address": address}

    chain, market = chains.resolve_chain(address)
    if not chain:
        out["error"] = ("no liquidity found on any enabled chain: "
                        + ", ".join(config.enabled_chains()))
        return out

    adapter = chains.get_adapter(chain)
    out["chain"] = chain
    out["adapter"] = adapter
    out["market"] = market

    safety = adapter.safety(address, market.pair_address)
    out["safety"] = safety

    social = 0.0
    try:
        social = len(store.channels_for(address)) or 0.0
    except Exception:
        pass

    smart = 0
    try:
        smart = smartmoney.recent_buys(chain, store).get(address, 0)
    except Exception:
        pass

    hot = {}
    try:
        hot = meta_mod.hot_terms(store)
    except Exception:
        pass

    ev = scoring.evaluate(market, safety, chain,
                          social_channels=social, smart_wallets=smart,
                          macro=smartmoney.macro_regime(), hot_meta=hot)
    out["evaluation"] = ev
    out["social"] = social
    out["smart"] = smart
    return out


# ── TEXT OUTPUT ───────────────────────────────────────────────────

def _bar(label: str, width: int = 62) -> str:
    return f"── {label} " + "─" * max(0, width - len(label) - 4)


def render(result: dict) -> str:
    if result.get("error"):
        return f"{result['address']}\n\n{result['error']}"

    m, s, ev = result["market"], result["safety"], result["evaluation"]
    ad, c = result["adapter"], result["evaluation"].conviction
    L = []

    L.append(f"{m.name} ({m.symbol})  ·  {ad.display}")
    L.append("")

    L.append(_bar("market"))
    L.append(f"  price      {alerts.price(m.price_usd)}")
    L.append(f"  liquidity  {alerts.money(m.liquidity_usd)}")
    L.append(f"  fdv        {alerts.money(m.fdv)}")
    L.append(f"  volume     24h {alerts.money(m.volume_24h)}   "
             f"1h {alerts.money(m.volume_1h)}   5m {alerts.money(m.volume_5m)}")
    L.append(f"  change     5m {alerts.pct(m.change_5m)}   "
             f"1h {alerts.pct(m.change_1h)}   24h {alerts.pct(m.change_24h)}")
    L.append(f"  txns 5m    {m.buys_5m} buys / {m.sells_5m} sells")
    L.append(f"  age        {alerts.age(m.age_hours, m.age_known)}")
    L.append(f"  dex        {m.dex or 'unknown'}"
             + (f"   launchpad {m.launchpad}" if m.launchpad else ""))
    issues = m.sanity_issues
    if issues:
        L.append(f"  data       SUSPECT — {', '.join(issues)}")

    L.append("")
    L.append(_bar("safety"))
    L.append(f"  verdict    {s.verdict}")
    L.append(f"  sources    {', '.join(s.sources) or 'none answered'}")
    for field, unit in (("top_holder_pct", "%"), ("top10_pct", "%"),
                        ("insider_pct", "%"), ("lp_locked_pct", "%"),
                        ("holder_count", ""), ("creator_holds_pct", "%"),
                        ("buy_tax_pct", "%"), ("sell_tax_pct", "%")):
        v = getattr(s, field, None)
        shown = (f"{v}{unit}" if v is not None
                 else ("UNAVAILABLE" if field in s.unavailable else "n/a"))
        L.append(f"  {field:<10} {shown}")
    if s.hard_rejects:
        L.append(f"  REJECTS    {', '.join(s.hard_rejects)}")

    flags = c.risk_flags
    L.append("")
    L.append(_bar("scam checks"))
    if not flags:
        L.append("  none")
    for f in flags:
        mark = "DANGER" if f.severity == "danger" else "warn  "
        L.append(f"  {mark}  {f.code:<14} {f.detail}  ({f.penalty})")

    L.append("")
    L.append(_bar("tier"))
    if ev.tier.matched:
        L.append(f"  matched    {ev.tier.tier}")
    else:
        L.append("  matched    none")
        for tier, fails in ev.tier.failures.items():
            L.append(f"  {tier:<12} {'; '.join(fails[:3])}")

    L.append("")
    L.append(_bar("conviction"))
    L.append(f"  score      {c.score}/100  ({c.band})")
    L.append(f"  momentum   {c.momentum}   launch {c.launch}")
    L.append(f"  narrative  {c.narrative}"
             + (f"   meta {c.meta_term}" if c.meta_term else ""))
    L.append(f"  context    session {c.session}   "
             f"social {result['social']:g}   smart money {result['smart']}")
    L.append(f"  breakdown  {c.explain() or 'nothing scored'}")

    L.append("")
    L.append(_bar("verdict"))
    if ev.should_alert:
        L.append(f"  ALERT — would reach Telegram "
                 f"({c.score} >= {config.CONVICTION['min_to_alert']})")
    elif ev.should_track:
        L.append(f"  TRACKED ONLY — recorded and watched, but below the "
                 f"alert bar ({c.score} < {config.CONVICTION['min_to_alert']})")
    else:
        L.append(f"  REJECTED by {ev.rejected_by} — {ev.reject_detail}")

    L.append("")
    L.append(f"  {ad.chart_url(m.ca)}")
    return "\n".join(L)


def render_telegram(result: dict) -> str:
    """Same analysis, formatted for the chat."""
    if result.get("error"):
        return (f"🔍 <b>Analysis</b>\n\n<code>{alerts.esc(result['address'])}</code>"
                f"\n\n{alerts.esc(result['error'])}")

    m, s, ev = result["market"], result["safety"], result["evaluation"]
    ad, c = result["adapter"], result["evaluation"].conviction

    if ev.should_alert:
        head, verdict = "🔥", "would alert"
    elif ev.should_track:
        head, verdict = "👀", "tracked, below alert bar"
    else:
        head, verdict = "🚫", f"rejected — {ev.rejected_by}"

    L = [
        f"{head} <b>{alerts.esc(m.name)}</b> ({alerts.esc(m.symbol)})",
        f"{alerts.esc(ad.display)} · {alerts.esc(verdict)}",
        "",
        f"⚡ <b>{c.score}/100</b> · {c.band} · {c.momentum} · {c.launch}",
        "",
        f"💧 Liq {alerts.money(m.liquidity_usd)}   📊 FDV {alerts.money(m.fdv)}",
        f"📈 5m {alerts.pct(m.change_5m)}  1h {alerts.pct(m.change_1h)}  "
        f"24h {alerts.pct(m.change_24h)}",
        f"🔁 {m.buys_5m}b / {m.sells_5m}s   🕐 {alerts.age(m.age_hours, m.age_known)}",
        "",
        f"🔐 {alerts.esc(s.display())}",
    ]

    if ev.rejected_by:
        L.append(f"🚫 {alerts.esc(ev.reject_detail)}")

    if c.risk_flags:
        L.append("")
        L.append("🚩 <b>Scam checks</b>")
        for f in c.risk_flags[:5]:
            mark = "🔴" if f.severity == "danger" else "🟡"
            L.append(f"{mark} {alerts.esc(f.code)} — {alerts.esc(f.detail)} "
                     f"({f.penalty})")

    if not ev.tier.matched and ev.tier.failures:
        first = ev.tier.failures.get("first_moon") or []
        if first:
            L.append("")
            L.append(f"📏 {alerts.esc('; '.join(first[:2]))}")

    L += [
        "",
        f"<i>{alerts.esc(c.explain() or 'nothing scored')}</i>",
        "",
        f"<code>{alerts.esc(m.ca)}</code>",
        "",
        f'<a href="{ad.chart_url(m.ca)}">chart</a> · '
        f'<a href="{ad.explorer_url(m.ca)}">explorer</a>',
    ]
    return "\n".join(L)


# ── TELEGRAM POLLING ──────────────────────────────────────────────

TELEGRAM_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"


def poll_once() -> int:
    """
    Answer any addresses sent to the bot since last time.

    Runs on the same cron as everything else rather than as a live listener,
    since scheduled jobs cannot hold a connection open. Worst case a reply
    takes as long as the gap between runs.
    """
    from chain_base import http_get

    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("TELEGRAM_BOT_TOKEN not set")
        return 1

    rows = store.select("bot_state", {"select": "value",
                                      "key": "eq.last_update_id", "limit": "1"})
    offset = int(rows[0]["value"]) + 1 if rows else 0

    data = http_get(TELEGRAM_UPDATES.format(token=token),
                    params={"offset": offset, "timeout": 0, "limit": 20})
    updates = (data or {}).get("result") or []
    if not updates:
        print("no new messages")
        return 0

    import social as social_mod
    handled = 0
    last_id = offset - 1

    for u in updates:
        last_id = max(last_id, int(u.get("update_id", 0)))
        msg = u.get("message") or u.get("channel_post") or {}
        text = msg.get("text") or ""
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        if not text or not chat_id:
            continue

        for addr in social_mod.extract_addresses(text)[:3]:
            print(f"analysing {addr} for chat {chat_id}")
            try:
                alerts.send(render_telegram(analyze(addr)), chat_id=chat_id)
                handled += 1
            except Exception as e:
                log.warning("analysis failed for %s: %s", addr, e)
                alerts.send(f"🔍 could not analyse <code>{alerts.esc(addr)}</code>"
                            f"\n{alerts.esc(str(e))}", chat_id=chat_id)

    store.upsert("bot_state", {"key": "last_update_id", "value": str(last_id)},
                 on_conflict="key")
    print(f"handled {handled} address(es) across {len(updates)} update(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Surgeon contract analyzer")
    ap.add_argument("address", nargs="?", help="contract address")
    ap.add_argument("--send", action="store_true", help="also send to Telegram")
    ap.add_argument("--poll", action="store_true",
                    help="answer addresses sent to the bot")
    args = ap.parse_args()

    if args.poll:
        return poll_once()
    if not args.address:
        ap.error("give an address, or --poll")

    started = time.time()
    result = analyze(args.address)
    print()
    print(render(result))
    print()
    print(f"  analysed in {time.time() - started:.1f}s")

    if args.send:
        res = alerts.send(render_telegram(result))
        print("  sent to telegram" if res.ok else f"  send failed: {res.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
