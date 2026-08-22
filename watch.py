#!/usr/bin/env python3
"""
Position watcher.

Every alerted token stays open until it resolves. This tracks them, notifies
on what happens, and writes the outcome back — which is what turns a scanner
into something that can learn.

    python3 watch.py              check all open positions
    python3 watch.py --chain base
    python3 watch.py --dry-run    evaluate and log, send nothing

Signal only: these are notifications about what a position did, not orders.
"""

from __future__ import annotations

import sys
import time
import logging
import argparse
from dataclasses import dataclass, field

import config
import chains
import chain_base
import alerts
from store import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("surgeon.watch")


# Events that end a position. The rest are milestones along the way.
# STOP_WARN is deliberately absent: it notifies without ending the position,
# so we keep observing and find out whether early dips recover.
TERMINAL = {"STOP_LOSS", "TRAIL_STOP", "DEV_SOLD", "WHALE_STOP",
            "VOLUME_FADE", "TIME_STOP", "MAX_HOLD"}


@dataclass
class WatchResult:
    checked: int = 0
    events: dict = field(default_factory=dict)
    closed: int = 0
    errors: int = 0

    def fire(self, event: str):
        self.events[event] = self.events.get(event, 0) + 1


def classify_outcome(final_pnl: float, peak_pnl: float) -> str:
    """
    Grade a closed position.

    Peak matters as well as the close: a token that ran 300% and gave it all
    back was a correct call badly exited, and lumping it in with tokens that
    never moved would poison every weight learned from this data.
    """
    if peak_pnl >= 200:
        return "MOON"
    if final_pnl >= 100:
        return "BIG_WIN"
    if final_pnl >= 50:
        return "WIN"
    if final_pnl > 0:
        return "WEAK_WIN"
    return "LOSS"


def _pnl(entry: float, current: float) -> float | None:
    """
    Percent change, or None when the inputs cannot be trusted.

    Returning None rather than a number matters: a near-zero entry price
    produces readings in the millions, and silently clamping them would
    record a fabricated outcome instead of admitting we do not know.
    """
    if entry <= 0 or current < 0:
        return None
    pct = (current - entry) / entry * 100.0
    if pct < config.WATCH["pnl_floor_pct"] or pct > config.WATCH["pnl_ceiling_pct"]:
        return None
    return pct


def evaluate_position(row: dict, market, adapter, fired: set[str],
                      safety=None) -> list[tuple[str, str]]:
    """
    Which events this position has newly triggered.

    Returns [(event, detail)]. Order matters — the first terminal event wins,
    so a token that gapped straight through TP1 to a stop reports both the
    milestone and the exit rather than silently only the exit.
    """
    W = config.WATCH
    entry = float(row.get("entry_price") or 0)
    if entry <= 0 or not market.ok:
        return []

    pnl = _pnl(entry, market.price_usd)
    if pnl is None:
        return []          # untrustworthy pricing — judge nothing
    peak_price = max(float(row.get("peak_price") or entry), market.price_usd)
    peak_pnl = _pnl(entry, peak_price) or 0.0
    held_hours = (time.time() - float(row.get("alerted_at") or 0)) / 3600

    out: list[tuple[str, str]] = []

    # -- milestones ------------------------------------------------
    for level, key in ((W["tp3_pct"], "TP3"),
                       (W["tp2_pct"], "TP2"),
                       (W["tp1_pct"], "TP1")):
        if pnl >= level and key not in fired:
            out.append((key, f"{market.symbol} up {pnl:+.0f}% since signal"))

    # -- dev wallet ------------------------------------------------
    # Compares the deployer's holding now against what it held when the
    # signal fired. An earlier version read a `dev_held` field that was never
    # written, so this could not fire at all.
    if safety is not None and "DEV_SOLD" not in fired and row.get("dev_held"):
        now_pct = safety.creator_holds_pct
        then_pct = float(row.get("creator_holds_pct") or 0)
        if now_pct is not None and then_pct > 0:
            dumped = (then_pct - now_pct) / then_pct
            if now_pct <= 0.01:
                out.append(("DEV_SOLD",
                            f"deployer wallet emptied — held {then_pct:.2f}% "
                            f"at signal"))
            elif dumped >= config.WATCH["dev_sold_fraction"]:
                out.append(("DEV_SOLD",
                            f"deployer sold {dumped:.0%} of its holding "
                            f"({then_pct:.2f}% -> {now_pct:.2f}%)"))

    # -- whale concentration appearing after entry -----------------
    if (safety is not None and "WHALE_STOP" not in fired
            and held_hours >= W["whale_recheck_hours"]
            and pnl >= W["whale_recheck_min_pnl"]):
        top = safety.top_holder_pct
        if top is not None and top >= W["whale_top_holder_pct"]:
            out.append(("WHALE_STOP",
                        f"top holder now {top:.0f}% — concentration built after entry"))

    # -- momentum dying while in profit ----------------------------
    if "VOLUME_FADE" not in fired and pnl >= W["volume_fade_min_pnl"]:
        hourly_avg = market.volume_1h / 12 if market.volume_1h else 0
        if hourly_avg > 0 and market.volume_5m < hourly_avg * W["volume_fade_ratio"]:
            out.append(("VOLUME_FADE",
                        f"5m volume {market.volume_5m:,.0f} vs {hourly_avg:,.0f} "
                        f"hourly average — momentum fading while up {pnl:+.0f}%"))

    # -- graduation: hold rather than exit -------------------------
    # Only meaningful for a token still on a bonding curve. FDV divided by
    # the graduation threshold is nonsense for anything already trading on a
    # normal AMM, and doubly so on chains that have no curve at all — it was
    # firing on every position and suppressing legitimate time stops.
    GRADUATED_DEXES = {"pumpswap", "raydium", "meteora", "orca", "uniswap",
                       "pancakeswap"}
    graduating = False
    on_curve = (market.launchpad == "pumpfun"
                and (market.dex or "").lower() not in GRADUATED_DEXES)
    if on_curve and market.fdv > 0:
        bc_pct = min(100.0, market.fdv / 85_000 * 100)
        graduating = bc_pct >= W["graduation_bc_pct"]
        if graduating and "GRADUATION" not in fired:
            out.append(("GRADUATION",
                        f"bonding curve ~{bc_pct:.0f}% — approaching graduation"))

    # -- stops -----------------------------------------------------
    took_tp2 = "TP2" in fired or any(e == "TP2" for e, _ in out)
    armed = peak_pnl >= W["trail_arm_pct"]
    ratio = W["give_back_after_tp2"] if took_tp2 else W["give_back_ratio"]
    floor = peak_pnl * (1 - ratio)

    if armed and pnl <= floor:
        given = 100 * (peak_pnl - pnl) / peak_pnl if peak_pnl else 0
        out.append(("TRAIL_STOP",
                    f"gave back {given:.0f}% of a {peak_pnl:+.0f}% peak, "
                    f"now {pnl:+.0f}%"))
    elif not armed:
        held_minutes = held_hours * 60
        if pnl <= W["stop_warn_pct"] and "STOP_WARN" not in fired:
            out.append(("STOP_WARN",
                        f"down {pnl:.0f}% since signal — still watching"))
        # Grading waits: a token minutes old swings on ordinary noise, and
        # closing it as a loss there records a verdict we have not earned.
        if pnl <= W["stop_loss_pct"] and held_minutes >= W["stop_grace_minutes"]:
            out.append(("STOP_LOSS",
                        f"down {pnl:.0f}% after {held_minutes:.0f}m"))

    # -- time -------------------------------------------------------
    # Graduation overrides time stops: a token about to graduate is doing
    # something, even if it has been slow about it.
    if not graduating:
        if held_hours >= W["time_stop_hours"] and pnl <= -5 and "TP1" not in fired:
            out.append(("TIME_STOP",
                        f"{held_hours:.1f}h held, still {pnl:+.0f}%"))
        elif held_hours >= W["time_exit_hours"] and pnl <= 10 and "TP2" not in fired:
            out.append(("TIME_STOP",
                        f"{held_hours:.1f}h held, flat at {pnl:+.0f}%"))

    if held_hours >= W["max_hold_hours"]:
        out.append(("MAX_HOLD", f"{held_hours:.1f}h — closing out"))

    return out


def watch_chain(chain: str, rows: list[dict], dry_run: bool) -> WatchResult:
    res = WatchResult()
    if not rows:
        return res

    adapter = chains.get_adapter(chain)
    cas = [r["ca"] for r in rows if r.get("ca")]
    markets = chain_base.dexscreener_markets(
        cas, chain, config.CHAINS[chain]["dexscreener_id"])

    for row in rows:
        ca = row.get("ca")
        if not ca:
            continue
        try:
            market = markets.get(ca)
            entry = float(row.get("entry_price") or 0)

            # A pair that has vanished is not a neutral outcome.
            if not market or not market.ok or market.liquidity_usd <= 0:
                store.close_position(ca, "LOSS", "RUGGED", final_pnl=-100.0,
                                     peak_pnl=float(row.get("peak_pnl") or 0))
                res.closed += 1
                res.fire("RUGGED")
                if not dry_run and row.get("alert_sent"):
                    alerts.send(alerts.format_watch(
                        "STOP_LOSS", row.get("name") or ca[:10], ca, -100.0,
                        adapter, "liquidity gone — position marked rugged"))
                continue

            res.checked += 1
            pnl = _pnl(entry, market.price_usd)
            if pnl is None:
                # Close it out of the tracking set, but never let a fabricated
                # number into the outcome data the weights are learned from.
                store.close_position(ca, "DATA_ERROR", "BAD_PRICING",
                                     final_pnl=0.0, peak_pnl=0.0)
                res.closed += 1
                res.fire("DATA_ERROR")
                log.warning("[%s] %s closed as DATA_ERROR — entry %.12f, "
                            "current %.12f", chain,
                            row.get("symbol") or ca[:10], entry,
                            market.price_usd)
                continue
            peak_price = max(float(row.get("peak_price") or entry),
                             market.price_usd)
            peak_pnl = _pnl(entry, peak_price) or 0.0

            fired = store.fired_watch_events(ca)

            # Safety is only re-pulled when an event could depend on it.
            safety = None
            held_hours = (time.time() - float(row.get("alerted_at") or 0)) / 3600
            whale_due = (held_hours >= config.WATCH["whale_recheck_hours"]
                         and pnl >= config.WATCH["whale_recheck_min_pnl"]
                         and "WHALE_STOP" not in fired)
            # A deployer dumping is worth knowing about immediately, not only
            # once a position is hours old and in profit.
            dev_due = bool(row.get("dev_held")) and "DEV_SOLD" not in fired
            if whale_due or dev_due:
                safety = adapter.safety(ca, market.pair_address)

            events = evaluate_position(row, market, adapter, fired, safety)

            # Persist the running peak even when nothing fired.
            if peak_price > float(row.get("peak_price") or 0):
                store.update("signals", {"ca": ca, "outcome": "pending"},
                             {"peak_price": peak_price, "peak_pnl": peak_pnl})

            # Positions scoring below the alert bar are tracked and graded
            # for the outcome data, but were never announced — so a TP alert
            # on one arrives about a token King has never heard of.
            announced = bool(row.get("alert_sent"))

            for event, detail in events:
                res.fire(event)
                log.info("[%s] %s %s — %s%s", chain, event,
                         row.get("symbol") or ca[:10], detail,
                         "" if announced else "  [tracked only, not sent]")
                store.mark_watch_event(ca, event, pnl)
                if not dry_run and announced:
                    alerts.send(alerts.format_watch(
                        event, row.get("name") or ca[:10], ca, pnl,
                        adapter, detail))

                if event in TERMINAL:
                    outcome = classify_outcome(pnl, peak_pnl)
                    store.close_position(ca, outcome, event, pnl, peak_pnl)
                    res.closed += 1
                    log.info("[%s] CLOSED %s as %s (final %+.0f%%, peak %+.0f%%)",
                             chain, row.get("symbol") or ca[:10], outcome,
                             pnl, peak_pnl)
                    break

        except Exception as e:
            log.warning("[%s] %s failed: %s", chain, str(ca)[:12], e)
            res.errors += 1

    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Surgeon position watcher")
    ap.add_argument("--chain", help="single chain")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and log, send nothing (default)")
    ap.add_argument("--live", action="store_true",
                    help="send alerts; also needs SURGEON_LIVE=true")
    args = ap.parse_args()

    sending = args.live and config.LIVE_ALERTS and not args.dry_run
    if args.live and not config.LIVE_ALERTS:
        log.warning("--live passed but SURGEON_LIVE is not 'true' — staying dry")
    dry_run = not sending

    started = time.time()
    log.info("position watch starting — %s", "LIVE" if sending else "DRY RUN")

    open_rows = store.open_positions(args.chain)
    if not open_rows:
        log.info("no open positions")
        return 0

    by_chain: dict[str, list[dict]] = {}
    for r in open_rows:
        if r.get("chain"):
            by_chain.setdefault(r["chain"], []).append(r)

    announced = sum(1 for r in open_rows if r.get("alert_sent"))
    log.info("watching %d positions across %d chains "
             "(%d announced, %d tracked silently)",
             len(open_rows), len(by_chain), announced,
             len(open_rows) - announced)

    results = {}
    for chain, rows in by_chain.items():
        try:
            results[chain] = watch_chain(chain, rows, dry_run)
        except Exception as e:
            log.error("[%s] watch crashed: %s", chain, e)

    print("\n" + "=" * 62)
    print("WATCH SUMMARY")
    print("=" * 62)
    total_events = total_closed = 0
    for chain, r in results.items():
        total_closed += r.closed
        total_events += sum(r.events.values())
        detail = ", ".join(f"{k}×{v}" for k, v in
                           sorted(r.events.items(), key=lambda x: -x[1])) or "-"
        print(f"  {config.CHAINS[chain]['display']:<18} "
              f"open {r.checked:>3}  closed {r.closed:>2}   {detail}")
    print("-" * 62)
    print(f"  {total_events} event(s), {total_closed} closed "
          f"in {time.time() - started:.0f}s")

    stats = store.stats()
    if stats["trades"]:
        print(f"  lifetime: {stats['trades']} closed, "
              f"{stats['win_rate']}% win rate")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
