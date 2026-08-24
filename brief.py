#!/usr/bin/env python3
"""
Daily briefing.

Everything King has been running by hand each morning, arriving on its own.
That matters more than convenience: a number nobody thinks to check is a
number that drifts, and several of the faults found this week — boosted
sending nothing, dev-sold never firing, unproven firing on nothing — were
invisible precisely because they had to be asked about.

    python3 brief.py             print it
    python3 brief.py --send      and deliver it to Telegram
"""

from __future__ import annotations

import sys
import time
import logging
import argparse
from collections import defaultdict

import config
import alerts
import meta as meta_mod
import smartmoney
from chain_base import safe_float
from store import store

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("surgeon.brief")

WINS = ("WIN", "BIG_WIN", "MOON", "WEAK_WIN")
EXCLUDED = ("pending", "BACKLOG_UNTRACKED", "DATA_ERROR")


def _rate(rows, key=lambda r: True) -> tuple[int, float]:
    sel = [r for r in rows if key(r)]
    if not sel:
        return 0, 0.0
    won = sum(1 for r in sel if str(r.get("outcome", "")).upper() in WINS)
    return len(sel), round(100.0 * won / len(sel), 1)


def gather(hours: int = 24) -> dict:
    """Everything the briefing reports on, in one pass over the data."""
    cutoff = time.time() - hours * 3600

    closed = [r for r in store.select("signals", {
        "select": "chain,tier,band,conviction,outcome,peak_pnl,final_pnl,"
                  "exit_type,alert_sent,from_watchlist,breakdown,closed_at",
        "outcome": f"not.in.({','.join(EXCLUDED)})",
        "order": "closed_at.desc",
        "limit": "2000",
    }) if safe_float(r.get("closed_at")) >= cutoff]

    sent = [r for r in store.select("signals", {
        "select": "chain,tier,conviction,name,symbol,alert_sent,alerted_at,peak_pnl",
        "alerted_at": f"gte.{cutoff}",
        "order": "conviction.desc",
        "limit": "500",
    })]

    open_now = store.open_positions()

    return {
        "hours": hours,
        "closed": closed,
        "sent": [r for r in sent if r.get("alert_sent")],
        "tracked": [r for r in sent if not r.get("alert_sent")],
        "open": open_now,
        "watchlist": store.watchlist_size(),
        "stats": store.stats(),
    }


def compose(d: dict) -> str:
    """The briefing, as Telegram HTML."""
    closed, sent = d["closed"], d["sent"]
    n, rate = _rate(closed)
    L = [f"🏥 <b>Surgeon — last {d['hours']}h</b>", ""]

    # -- the headline ---------------------------------------------
    if n:
        green = sum(1 for r in closed if safe_float(r.get("peak_pnl")) > 0)
        avg_peak = sum(safe_float(r.get("peak_pnl")) for r in closed) / n
        L += [f"📊 <b>{n} closed · {rate}% won</b>",
              f"    {green} went green · avg peak {avg_peak:+.0f}%"]
    else:
        L.append("📊 nothing closed")
    L.append(f"📤 {len(sent)} alerts sent · {len(d['tracked'])} tracked quietly")
    L.append(f"👀 {len(d['open'])} open · {d['watchlist']} parked")

    # -- by chain --------------------------------------------------
    by_chain = defaultdict(list)
    for r in closed:
        by_chain[r.get("chain")].append(r)
    if by_chain:
        L += ["", "⛓ <b>By chain</b>"]
        ranked = sorted(by_chain.items(),
                        key=lambda kv: -_rate(kv[1])[1])
        for chain, rows in ranked:
            c_n, c_rate = _rate(rows)
            peak = sum(safe_float(r.get("peak_pnl")) for r in rows) / c_n
            name = config.CHAINS.get(chain, {}).get("display", chain)
            L.append(f"    {alerts.esc(name)}: {c_n} · {c_rate}% · "
                     f"peak {peak:+.0f}%")

    # -- by tier ---------------------------------------------------
    by_tier = defaultdict(list)
    for r in closed:
        by_tier[r.get("tier")].append(r)
    if by_tier:
        L += ["", "🎯 <b>By tier</b>"]
        for tier, rows in sorted(by_tier.items(), key=lambda kv: -len(kv[1])):
            t_n, t_rate = _rate(rows)
            L.append(f"    {alerts.esc(str(tier))}: {t_n} · {t_rate}%")

    # -- exits -----------------------------------------------------
    exits = defaultdict(list)
    for r in closed:
        if r.get("exit_type"):
            exits[r["exit_type"]].append(r)
    if exits:
        L += ["", "🚪 <b>Exits</b>"]
        for kind, rows in sorted(exits.items(), key=lambda kv: -len(kv[1]))[:5]:
            peak = sum(safe_float(r.get("peak_pnl")) for r in rows) / len(rows)
            final = sum(safe_float(r.get("final_pnl")) for r in rows) / len(rows)
            L.append(f"    {alerts.esc(kind)}: {len(rows)} · "
                     f"peak {peak:+.0f}% → close {final:+.0f}%")

    # -- best of the day -------------------------------------------
    best = sorted(closed, key=lambda r: -safe_float(r.get("peak_pnl")))[:3]
    if best and safe_float(best[0].get("peak_pnl")) > 0:
        L += ["", "🏆 <b>Best</b>"]
        for r in best:
            heard = "" if r.get("alert_sent") else "  <i>(not sent)</i>"
            L.append(f"    {alerts.esc(r.get('symbol') or '?')} "
                     f"{safe_float(r.get('peak_pnl')):+.0f}% · "
                     f"{r.get('conviction')}/100{heard}")

    # -- context ---------------------------------------------------
    try:
        hot = meta_mod.hot_terms(store)
        top = sorted(hot.items(), key=lambda x: -x[1])[:4]
        if top:
            L += ["", "🔥 <b>Meta</b>: " +
                  alerts.esc(", ".join(t for t, _ in top))]
    except Exception:
        pass

    try:
        L.append(f"🌍 <b>Macro</b>: {smartmoney.macro_regime()}")
    except Exception:
        pass

    lifetime = d["stats"]
    if lifetime.get("trades"):
        L += ["", f"<i>Lifetime: {lifetime['trades']} closed · "
                  f"{lifetime['win_rate']}% won</i>"]

    # -- anything that looks broken --------------------------------
    warnings = health(d)
    if warnings:
        L += ["", "⚠️ <b>Worth checking</b>"]
        L += [f"    {alerts.esc(w)}" for w in warnings]

    return "\n".join(L)


def health(d: dict) -> list[str]:
    """
    Conditions that are usually a fault rather than a quiet market.

    Each of these was a real bug found this week only because someone thought
    to look: a tier sending nothing, an exit never firing, a rule matching
    nothing at all.
    """
    out = []
    closed, sent = d["closed"], d["sent"]

    if not sent and closed:
        out.append("nothing alerted — floors may be too high")

    tiers_sent = {r.get("tier") for r in sent}
    for tier in ("first_moon", "second_moon", "boosted"):
        if tier in {r.get("tier") for r in d["tracked"]} and tier not in tiers_sent:
            out.append(f"{tier} tracked but never sent")

    if len(d["open"]) == 0 and sent:
        out.append("alerts sent but nothing being watched")

    exits = {r.get("exit_type") for r in closed}
    if closed and "LIQUIDITY_DRAIN" not in exits and any(
            r.get("exit_type") == "RUGGED" for r in closed):
        out.append("rugs closing as RUGGED, not caught draining")

    n, rate = _rate(closed)
    if n >= 20 and rate < 10:
        out.append(f"win rate {rate}% over {n} trades")

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Surgeon daily briefing")
    ap.add_argument("--send", action="store_true", help="deliver to Telegram")
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()

    d = gather(args.hours)
    text = compose(d)

    # Readable in a terminal as well as in the chat.
    import re
    print(re.sub(r"<[^>]+>", "", text))

    if args.send:
        res = alerts.send(text)
        print("\nsent" if res.ok else f"\nsend failed: {res.error}")
        return 0 if res.ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
